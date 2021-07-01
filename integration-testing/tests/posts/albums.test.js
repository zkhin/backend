import dayjs from 'dayjs'
import got from 'got'
import {v4 as uuidv4} from 'uuid'

import {cognito, eventually, generateRandomJpeg, sleep} from '../../utils'
import {mutations, queries} from '../../schema'

const imageBytes = generateRandomJpeg(8, 8)
const imageData = new Buffer.from(imageBytes).toString('base64')
const imageHeaders = {'Content-Type': 'image/jpeg'}
const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})
beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.reset())

test('Create a posts in an album, album post ordering', async () => {
  const {client: ourClient} = await loginCache.getCleanLogin()

  // we add an album
  const albumId = uuidv4()
  await ourClient
    .mutate({mutation: mutations.addAlbum, variables: {albumId, name: 'n'}})
    .then(({data: {addAlbum: album}}) => {
      expect(album).toMatchObject({albumId, postCount: 0, postsLastUpdatedAt: null, posts: {items: []}})
    })

  // we add an image post in that album
  const postId1 = uuidv4()
  const postedAt = await ourClient
    .mutate({mutation: mutations.addPost, variables: {postId: postId1, albumId, imageData}})
    .then(({data: {addPost: post}}) => {
      expect(post).toMatchObject({postId: postId1, postedAt: expect.anything()})
      return dayjs(post.postedAt)
    })

  // check the album
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.album, variables: {albumId}})
    expect(data.album.albumId).toBe(albumId)
    expect(data.album.postCount).toBe(1)
    expect(dayjs(data.album.postsLastUpdatedAt) - postedAt).toBeGreaterThan(0)
    expect(dayjs(data.album.postsLastUpdatedAt) - dayjs()).toBeLessThan(0)
    expect(data.album.posts.items).toHaveLength(1)
    expect(data.album.posts.items[0].postId).toBe(postId1)
  })

  // we add another image post in that album, this one via cloudfront upload
  const postId2 = uuidv4()
  const uploadUrl = await ourClient
    .mutate({mutation: mutations.addPost, variables: {postId: postId2, albumId}})
    .then(({data: {addPost: post}}) => {
      expect(post).toMatchObject({postId: postId2, imageUploadUrl: expect.anything()})
      return post.imageUploadUrl
    })
  const before = dayjs()
  await got.put(uploadUrl, {headers: imageHeaders, body: imageBytes})

  // check the album
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.album, variables: {albumId}})
    expect(data.album.albumId).toBe(albumId)
    expect(data.album.postCount).toBe(2)
    expect(dayjs(data.album.postsLastUpdatedAt) - before).toBeGreaterThan(0)
    expect(dayjs(data.album.postsLastUpdatedAt) - dayjs()).toBeLessThan(0)
    expect(data.album.posts.items).toHaveLength(2)
    expect(data.album.posts.items[0].postId).toBe(postId1)
    expect(data.album.posts.items[1].postId).toBe(postId2)
  })

  // we a text-only post in that album
  const postId3 = uuidv4()
  await ourClient
    .mutate({
      mutation: mutations.addPost,
      variables: {postId: postId3, albumId, text: 'lore ipsum', postType: 'TEXT_ONLY'},
    })
    .then(({data: {addPost: post}}) => expect(post).toMatchObject({postId: postId3}))

  // check the album
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.album, variables: {albumId}})
    expect(data.album.albumId).toBe(albumId)
    expect(data.album.postCount).toBe(3)
    expect(data.album.posts.items).toHaveLength(3)
    expect(data.album.posts.items[0].postId).toBe(postId1)
    expect(data.album.posts.items[1].postId).toBe(postId2)
    expect(data.album.posts.items[2].postId).toBe(postId3)
  })
})

test('Cant create post in or move post into album that doesnt exist', async () => {
  const {client: ourClient} = await loginCache.getCleanLogin()
  const albumId = uuidv4() // doesn't exist

  // verify we cannot create a post in that album
  const postId = uuidv4()
  let variables = {postId, albumId}
  await expect(ourClient.mutate({mutation: mutations.addPost, variables})).rejects.toThrow(
    /ClientError: Album .* does not exist/,
  )

  // make sure that post did not end making it into the DB
  let resp = await ourClient.query({query: queries.post, variables: {postId}})
  expect(resp.data.post).toBeNull()

  // we create a post, not in any album
  resp = await ourClient.mutate({mutation: mutations.addPost, variables: {postId}})
  expect(resp.data.addPost.postId).toBe(postId)
  expect(resp.data.addPost.album).toBeNull()

  // verify neither we or them cannot move into no album
  variables = {postId, albumId}
  await expect(ourClient.mutate({mutation: mutations.editPostAlbum, variables})).rejects.toThrow(
    /ClientError: Album .* does not exist/,
  )

  // verify the post is unchanged
  resp = await ourClient.query({query: queries.post, variables: {postId}})
  expect(resp.data.post.postId).toBe(postId)
  expect(resp.data.post.album).toBeNull()
})

test('Cant create post in or move post into an album thats not ours', async () => {
  const {client: ourClient} = await loginCache.getCleanLogin()
  const {client: theirClient} = await loginCache.getCleanLogin()

  // they create an album
  const albumId = uuidv4()
  let resp = await theirClient.mutate({mutation: mutations.addAlbum, variables: {albumId, name: 'n1'}})
  expect(resp.data.addAlbum.albumId).toBe(albumId)

  // verify we cannot create a post in their album
  const postId = uuidv4()
  let variables = {postId, albumId}
  await expect(ourClient.mutate({mutation: mutations.addPost, variables})).rejects.toThrow(
    /ClientError: Album .* does not belong to caller /,
  )

  // make sure that post did not end making it into the DB
  resp = await theirClient.query({query: queries.post, variables: {postId}})
  expect(resp.data.post).toBeNull()

  // we create a post, not in any album
  resp = await ourClient.mutate({mutation: mutations.addPost, variables: {postId}})
  expect(resp.data.addPost.postId).toBe(postId)
  expect(resp.data.addPost.album).toBeNull()
  let uploadUrl = resp.data.addPost.imageUploadUrl
  await got.put(uploadUrl, {headers: imageHeaders, body: imageBytes})
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.post, variables: {postId}})
    expect(data.post.postStatus).toBe('COMPLETED')
  })

  // verify neither we or them cannot move the post into their album
  variables = {postId, albumId}
  await expect(ourClient.mutate({mutation: mutations.editPostAlbum, variables})).rejects.toThrow(
    /ClientError: Album .* belong to /,
  )
  await expect(theirClient.mutate({mutation: mutations.editPostAlbum, variables})).rejects.toThrow(
    /ClientError: Cannot edit another user's post/,
  )

  // verify the post is unchanged
  resp = await theirClient.query({query: queries.post, variables: {postId}})
  expect(resp.data.post.postId).toBe(postId)
  expect(resp.data.post.album).toBeNull()
})

test('Adding a post with PENDING status does not affect Album.posts until COMPLETED', async () => {
  const {client: ourClient} = await loginCache.getCleanLogin()

  // we add an album
  const albumId = uuidv4()
  let resp = await ourClient.mutate({mutation: mutations.addAlbum, variables: {albumId, name: 'n'}})
  expect(resp.data.addAlbum.albumId).toBe(albumId)
  expect(resp.data.addAlbum.postCount).toBe(0)
  expect(resp.data.addAlbum.postsLastUpdatedAt).toBeNull()
  expect(resp.data.addAlbum.posts.items).toHaveLength(0)

  // we add a image post in that album (in PENDING state)
  const postId = uuidv4()
  resp = await ourClient.mutate({mutation: mutations.addPost, variables: {postId, albumId}})
  expect(resp.data.addPost.postId).toBe(postId)
  expect(resp.data.addPost.postStatus).toBe('PENDING')
  expect(resp.data.addPost.album.albumId).toBe(albumId)
  const uploadUrl = resp.data.addPost.imageUploadUrl

  // check the album's posts, should not see the new post
  await sleep()
  await ourClient.query({query: queries.album, variables: {albumId}}).then(({data}) => {
    expect(data.album.albumId).toBe(albumId)
    expect(data.album.postCount).toBe(0)
    expect(data.album.postsLastUpdatedAt).toBeNull()
    expect(data.album.posts.items).toHaveLength(0)
  })

  // upload the image, thus completing the post
  await got.put(uploadUrl, {headers: imageHeaders, body: imageBytes})

  // check the album's posts, *should* see the new post
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.album, variables: {albumId}})
    expect(data.album.albumId).toBe(albumId)
    expect(data.album.postCount).toBe(1)
    expect(data.album.postsLastUpdatedAt).toBeTruthy()
    expect(data.album.posts.items).toHaveLength(1)
    expect(data.album.posts.items[0].postId).toBe(postId)
  })
})

test('Add, remove, change albums for an existing post', async () => {
  const {client: ourClient} = await loginCache.getCleanLogin()

  // add two albums
  const [albumId1, albumId2] = [uuidv4(), uuidv4()]
  let resp = await ourClient.mutate({mutation: mutations.addAlbum, variables: {albumId: albumId1, name: 'n1'}})
  expect(resp.data.addAlbum.albumId).toBe(albumId1)
  resp = await ourClient.mutate({mutation: mutations.addAlbum, variables: {albumId: albumId2, name: 'n2'}})
  expect(resp.data.addAlbum.albumId).toBe(albumId2)

  // add a post, not in any album
  const postId = uuidv4()
  resp = await ourClient.mutate({mutation: mutations.addPost, variables: {postId, imageData}})
  expect(resp.data.addPost.postId).toBe(postId)
  expect(resp.data.addPost.postStatus).toBe('COMPLETED')
  expect(resp.data.addPost.album).toBeNull()

  // move that post into the 2nd album
  let before = dayjs()
  resp = await ourClient.mutate({mutation: mutations.editPostAlbum, variables: {postId, albumId: albumId2}})
  expect(resp.data.editPostAlbum.postId).toBe(postId)
  expect(resp.data.editPostAlbum.album.albumId).toBe(albumId2)

  // check the second album
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.album, variables: {albumId: albumId2}})
    expect(data.album.albumId).toBe(albumId2)
    expect(data.album.postCount).toBe(1)
    expect(data.album.posts.items).toHaveLength(1)
    expect(data.album.posts.items[0].postId).toBe(postId)
    expect(dayjs(data.album.postsLastUpdatedAt) - before).toBeGreaterThan(0)
    expect(dayjs(data.album.postsLastUpdatedAt) - dayjs()).toBeLessThan(0)
  })

  // add an unrelated text-only post to the first album
  const postId2 = uuidv4()
  let variables = {postId: postId2, albumId: albumId1, text: 'lore ipsum', postType: 'TEXT_ONLY'}
  resp = await ourClient.mutate({mutation: mutations.addPost, variables})
  expect(resp.data.addPost.postId).toBe(postId2)
  expect(resp.data.addPost.postStatus).toBe('COMPLETED')
  expect(resp.data.addPost.album.albumId).toBe(albumId1)

  // move the original post out of the 2nd album and into the first
  before = dayjs()
  resp = await ourClient.mutate({mutation: mutations.editPostAlbum, variables: {postId, albumId: albumId1}})
  expect(resp.data.editPostAlbum.postId).toBe(postId)
  expect(resp.data.editPostAlbum.album.albumId).toBe(albumId1)

  // check the 2nd album
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.album, variables: {albumId: albumId2}})
    expect(data.album.albumId).toBe(albumId2)
    expect(data.album.postCount).toBe(0)
    expect(data.album.posts.items).toHaveLength(0)
    expect(dayjs(data.album.postsLastUpdatedAt) - before).toBeGreaterThan(0)
    expect(dayjs(data.album.postsLastUpdatedAt) - dayjs()).toBeLessThan(0)
  })

  // check the first album, including post order - new post should be at the back
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.album, variables: {albumId: albumId1}})
    expect(data.album.albumId).toBe(albumId1)
    expect(data.album.postCount).toBe(2)
    expect(data.album.posts.items).toHaveLength(2)
    expect(data.album.posts.items[0].postId).toBe(postId2)
    expect(data.album.posts.items[1].postId).toBe(postId)
    expect(dayjs(data.album.postsLastUpdatedAt) - before).toBeGreaterThan(0)
    expect(dayjs(data.album.postsLastUpdatedAt) - dayjs()).toBeLessThan(0)
  })

  // remove the post from that album
  before = dayjs()
  resp = await ourClient.mutate({mutation: mutations.editPostAlbum, variables: {postId, albumId: null}})
  expect(resp.data.editPostAlbum.postId).toBe(postId)
  expect(resp.data.editPostAlbum.album).toBeNull()

  // check the first album
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.album, variables: {albumId: albumId1}})
    expect(data.album.albumId).toBe(albumId1)
    expect(data.album.postCount).toBe(1)
    expect(data.album.posts.items).toHaveLength(1)
    expect(data.album.posts.items[0].postId).toBe(postId2)
    expect(dayjs(data.album.postsLastUpdatedAt) - before).toBeGreaterThan(0)
    expect(dayjs(data.album.postsLastUpdatedAt) - dayjs()).toBeLessThan(0)
  })
})

// TODO: define behavior here. It's probably ok to let vido posts into albums, as they now have 'poster' images
test.skip('Cant add video post to album (yet)', async () => {
  const {client: ourClient} = await loginCache.getCleanLogin()

  // add an albums
  const albumId = uuidv4()
  let resp = await ourClient.mutate({mutation: mutations.addAlbum, variables: {albumId: albumId, name: 'n1'}})
  expect(resp.data.addAlbum.albumId).toBe(albumId)

  // verify can't create video post in that album
  const postId = uuidv4()
  await expect(
    ourClient.mutate({mutation: mutations.addPost, variables: {postId, postType: 'VIDEO', albumId}}),
  ).rejects.toThrow('ClientError lsadfkjasldkfj')

  // create the video post
  resp = ourClient.mutate({mutation: mutations.addPost, variables: {postId, postType: 'VIDEO'}})
  expect(resp.data.addPost.postId).toBe(postId)

  // verify can't move the video post into that album
  await expect(
    ourClient.mutate({mutation: mutations.editPostAlbum, variables: {postId, albumId}}),
  ).rejects.toThrow('ClientError lsadfkjasldkfj')
})

test('Adding an existing post to album not in COMPLETED status has no affect on Album.post & friends', async () => {
  const {client: ourClient} = await loginCache.getCleanLogin()

  // add an albums
  const albumId = uuidv4()
  let resp = await ourClient.mutate({mutation: mutations.addAlbum, variables: {albumId, name: 'n1'}})
  expect(resp.data.addAlbum.albumId).toBe(albumId)

  // add an image post, leave it in PENDING state
  const postId1 = uuidv4()
  resp = await ourClient.mutate({mutation: mutations.addPost, variables: {postId: postId1}})
  expect(resp.data.addPost.postId).toBe(postId1)
  expect(resp.data.addPost.postStatus).toBe('PENDING')

  // add an image post, and archive it
  const postId2 = uuidv4()
  let variables = {postId: postId2, imageData}
  resp = await ourClient.mutate({mutation: mutations.addPost, variables})
  expect(resp.data.addPost.postId).toBe(postId2)
  resp = await ourClient.mutate({mutation: mutations.archivePost, variables: {postId: postId2}})
  expect(resp.data.archivePost.postId).toBe(postId2)
  expect(resp.data.archivePost.postStatus).toBe('ARCHIVED')

  // add post the PENDING and the ARCHIVED posts to the album
  resp = await ourClient.mutate({mutation: mutations.editPostAlbum, variables: {postId: postId1, albumId}})
  expect(resp.data.editPostAlbum.postId).toBe(postId1)
  expect(resp.data.editPostAlbum.album.albumId).toBe(albumId)
  resp = await ourClient.mutate({mutation: mutations.editPostAlbum, variables: {postId: postId2, albumId}})
  expect(resp.data.editPostAlbum.postId).toBe(postId2)
  expect(resp.data.editPostAlbum.album.albumId).toBe(albumId)

  // check that Album.posts & friends have not changed
  await sleep()
  await ourClient.query({query: queries.album, variables: {albumId}}).then(({data}) => {
    expect(data.album.albumId).toBe(albumId)
    expect(data.album.postCount).toBe(0)
    expect(data.album.postsLastUpdatedAt).toBeNull()
    expect(data.album.posts.items).toHaveLength(0)
  })
})

test('Archiving a post removes it from Album.posts & friends, restoring it does not maintain rank', async () => {
  const {client: ourClient} = await loginCache.getCleanLogin()

  // add an album
  const albumId = uuidv4()
  let resp = await ourClient.mutate({mutation: mutations.addAlbum, variables: {albumId, name: 'n1'}})
  expect(resp.data.addAlbum.albumId).toBe(albumId)

  // add an image post in the album
  const postId = uuidv4()
  let variables = {postId, albumId, imageData}
  resp = await ourClient.mutate({mutation: mutations.addPost, variables})
  expect(resp.data.addPost.postId).toBe(postId)
  expect(resp.data.addPost.postStatus).toBe('COMPLETED')
  expect(resp.data.addPost.album.albumId).toBe(albumId)

  // allow system to process that post
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.album, variables: {albumId}})
    expect(data.album.albumId).toBe(albumId)
    expect(data.album.postCount).toBe(1)
  })

  // add another image post in the album
  const postId2 = uuidv4()
  variables = {postId: postId2, albumId, imageData}
  resp = await ourClient.mutate({mutation: mutations.addPost, variables})
  expect(resp.data.addPost.postId).toBe(postId2)
  expect(resp.data.addPost.postStatus).toBe('COMPLETED')
  expect(resp.data.addPost.album.albumId).toBe(albumId)

  // verify that's reflected in Album.posts and friends
  let postsLastUpdatedAt = await eventually(async () => {
    const {data} = await ourClient.query({query: queries.album, variables: {albumId}})
    expect(data.album.albumId).toBe(albumId)
    expect(data.album.postCount).toBe(2)
    expect(data.album.posts.items).toHaveLength(2)
    expect(data.album.posts.items[0].postId).toBe(postId)
    expect(data.album.posts.items[1].postId).toBe(postId2)
    expect(data.album.postsLastUpdatedAt).toBeTruthy()
    return dayjs(data.album.postsLastUpdatedAt)
  })

  // archive the post
  resp = await ourClient.mutate({mutation: mutations.archivePost, variables: {postId}})
  expect(resp.data.archivePost.postId).toBe(postId)
  expect(resp.data.archivePost.postStatus).toBe('ARCHIVED')

  // verify that took it out of Album.post and friends
  postsLastUpdatedAt = await eventually(async () => {
    const {data} = await ourClient.query({query: queries.album, variables: {albumId}})
    expect(data.album.albumId).toBe(albumId)
    expect(data.album.postCount).toBe(1)
    expect(data.album.posts.items).toHaveLength(1)
    expect(data.album.posts.items[0].postId).toBe(postId2)
    expect(dayjs(data.album.postsLastUpdatedAt) - postsLastUpdatedAt).toBeGreaterThan(0)
    return dayjs(data.album.postsLastUpdatedAt)
  })

  // restore the post
  resp = await ourClient.mutate({mutation: mutations.restoreArchivedPost, variables: {postId}})
  expect(resp.data.restoreArchivedPost.postId).toBe(postId)
  expect(resp.data.restoreArchivedPost.postStatus).toBe('COMPLETED')

  // verify its now back in Album.posts and friends, in the back
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.album, variables: {albumId}})
    expect(data.album.albumId).toBe(albumId)
    expect(data.album.postCount).toBe(2)
    expect(data.album.posts.items).toHaveLength(2)
    expect(data.album.posts.items[0].postId).toBe(postId2)
    expect(data.album.posts.items[1].postId).toBe(postId)
    expect(dayjs(data.album.postsLastUpdatedAt) - postsLastUpdatedAt).toBeGreaterThan(0)
  })
})

test('Deleting a post removes it from Album.posts & friends', async () => {
  const {client: ourClient} = await loginCache.getCleanLogin()

  // add an albums
  const albumId = uuidv4()
  let resp = await ourClient.mutate({mutation: mutations.addAlbum, variables: {albumId, name: 'n1'}})
  expect(resp.data.addAlbum.albumId).toBe(albumId)

  // add an image post in the album
  const postId = uuidv4()
  let variables = {postId, albumId, imageData}
  resp = await ourClient.mutate({mutation: mutations.addPost, variables})
  expect(resp.data.addPost.postId).toBe(postId)
  expect(resp.data.addPost.postStatus).toBe('COMPLETED')
  expect(resp.data.addPost.album.albumId).toBe(albumId)

  // verify that's reflected in Album.posts and friends
  const postsLastUpdatedAt = await eventually(async () => {
    const {data} = await ourClient.query({query: queries.album, variables: {albumId}})
    expect(data.album.albumId).toBe(albumId)
    expect(data.album.postCount).toBe(1)
    expect(data.album.posts.items).toHaveLength(1)
    expect(data.album.posts.items[0].postId).toBe(postId)
    expect(data.album.postsLastUpdatedAt).toBeTruthy()
    return dayjs(data.album.postsLastUpdatedAt)
  })

  // delete the post
  resp = await ourClient.mutate({mutation: mutations.deletePost, variables: {postId}})
  expect(resp.data.deletePost.postId).toBe(postId)
  expect(resp.data.deletePost.postStatus).toBe('DELETING')

  // verify that took it out of Album.post and friends
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.album, variables: {albumId}})
    expect(data.album.albumId).toBe(albumId)
    expect(data.album.postCount).toBe(0)
    expect(data.album.posts.items).toHaveLength(0)
    expect(dayjs(data.album.postsLastUpdatedAt) - postsLastUpdatedAt).toBeGreaterThan(0)
  })
})

test('Edit album post order failures', async () => {
  const {client: ourClient} = await loginCache.getCleanLogin()
  const {client: theirClient} = await loginCache.getCleanLogin()
  const [albumId, albumId2, postId1, postId2, postId3] = [uuidv4(), uuidv4(), uuidv4(), uuidv4(), uuidv4()]

  // we add an album
  let variables = {albumId, name: 'n1'}
  let resp = await ourClient.mutate({mutation: mutations.addAlbum, variables})
  expect(resp.data.addAlbum.albumId).toBe(albumId)

  // they add nother album
  variables = {albumId: albumId2, name: 'n2'}
  resp = await theirClient.mutate({mutation: mutations.addAlbum, variables})
  expect(resp.data.addAlbum.albumId).toBe(albumId2)

  // we add two posts to the album
  variables = {postId: postId1, albumId, imageData}
  resp = await ourClient.mutate({mutation: mutations.addPost, variables})
  expect(resp.data.addPost.postId).toBe(postId1)

  variables = {postId: postId2, albumId, imageData}
  resp = await ourClient.mutate({mutation: mutations.addPost, variables})
  expect(resp.data.addPost.postId).toBe(postId2)

  // they add a post, in a different album
  variables = {postId: postId3, imageData, albumId: albumId2}
  resp = await theirClient.mutate({mutation: mutations.addPost, variables})
  expect(resp.data.addPost.postId).toBe(postId3)

  // check album post order
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.album, variables: {albumId}})
    expect(data.album).toBeTruthy()
    expect(data.album.albumId).toBe(albumId)
    expect(data.album.postCount).toBe(2)
    expect(data.album.posts.items).toHaveLength(2)
    expect(data.album.posts.items[0].postId).toBe(postId1)
    expect(data.album.posts.items[1].postId).toBe(postId2)
  })

  // verify they cannot change our album's post order
  variables = {postId: postId1, precedingPostId: postId2}
  await expect(theirClient.mutate({mutation: mutations.editPostAlbumOrder, variables})).rejects.toThrow(
    /ClientError: Cannot edit another /,
  )

  // verify they cannot use their post to change our order
  variables = {postId: postId3, precedingPostId: postId2}
  await expect(theirClient.mutate({mutation: mutations.editPostAlbumOrder, variables})).rejects.toThrow(
    /ClientError: .* does not belong to caller/,
  )

  // verify we cannot use their post to change our order
  variables = {postId: postId1, precedingPostId: postId3}
  await expect(ourClient.mutate({mutation: mutations.editPostAlbumOrder, variables})).rejects.toThrow(
    /ClientError: .* does not belong to caller/,
  )

  // check album post order has not changed
  await sleep()
  await ourClient.query({query: queries.album, variables: {albumId}}).then(({data}) => {
    expect(data.album.albumId).toBe(albumId)
    expect(data.album.postCount).toBe(2)
    expect(data.album.posts.items).toHaveLength(2)
    expect(data.album.posts.items[0].postId).toBe(postId1)
    expect(data.album.posts.items[1].postId).toBe(postId2)
  })

  // make sure post change order can actually complete without error
  variables = {postId: postId1, precedingPostId: postId2}
  resp = await ourClient.mutate({mutation: mutations.editPostAlbumOrder, variables})
  expect(resp.data.editPostAlbumOrder.postId).toBe(postId1)
  expect(resp.data.editPostAlbumOrder.album.albumId).toBe(albumId)
})

test('Edit album post order', async () => {
  const {client: ourClient} = await loginCache.getCleanLogin()
  const [albumId, postId1, postId2, postId3] = [uuidv4(), uuidv4(), uuidv4(), uuidv4()]

  // we add an album
  let variables = {albumId, name: 'n1'}
  let resp = await ourClient.mutate({mutation: mutations.addAlbum, variables})
  expect(resp.data.addAlbum.albumId).toBe(albumId)

  // album has the default art urls
  let album = await eventually(async () => {
    const {data} = await ourClient.query({query: queries.album, variables: {albumId}})
    expect(data.album).toBeTruthy()
    expect(data.album.albumId).toBe(albumId)
    expect(data.album.postCount).toBe(0)
    expect(data.album.posts.items).toHaveLength(0)
    return data.album
  })

  // we add three posts to the album
  variables = {postId: postId1, albumId, text: 'lore', postType: 'TEXT_ONLY'}
  resp = await ourClient.mutate({mutation: mutations.addPost, variables})
  expect(resp.data.addPost.postId).toBe(postId1)

  variables = {postId: postId2, albumId, imageData}
  resp = await ourClient.mutate({mutation: mutations.addPost, variables})
  expect(resp.data.addPost.postId).toBe(postId2)

  variables = {postId: postId3, albumId, text: 'ipsum', postType: 'TEXT_ONLY'}
  resp = await ourClient.mutate({mutation: mutations.addPost, variables})
  expect(resp.data.addPost.postId).toBe(postId3)

  // check album post order
  album = await eventually(async () => {
    const {data} = await ourClient.query({query: queries.album, variables: {albumId}})
    expect(data.album.albumId).toBe(albumId)
    expect(data.album.postCount).toBe(3)
    expect(data.album.posts.items).toHaveLength(3)
    expect(data.album.posts.items[0].postId).toBe(postId1)
    expect(data.album.posts.items[1].postId).toBe(postId2)
    expect(data.album.posts.items[2].postId).toBe(postId3)
    // verify the art urls changed
    expect(data.album.art.url.split('?')[0]).not.toBe(album.art.url.split('?')[0])
    expect(data.album.art.url4k.split('?')[0]).not.toBe(album.art.url4k.split('?')[0])
    expect(data.album.art.url1080p.split('?')[0]).not.toBe(album.art.url1080p.split('?')[0])
    expect(data.album.art.url480p.split('?')[0]).not.toBe(album.art.url480p.split('?')[0])
    expect(data.album.art.url64p.split('?')[0]).not.toBe(album.art.url64p.split('?')[0])
    return data.album
  })

  // move the posts around a bit
  variables = {postId: postId3, precedingPostId: null}
  resp = await ourClient.mutate({mutation: mutations.editPostAlbumOrder, variables})
  expect(resp.data.editPostAlbumOrder.postId).toBe(postId3)

  // check album post order
  album = await eventually(async () => {
    const {data} = await ourClient.query({query: queries.album, variables: {albumId}})
    expect(data.album.albumId).toBe(albumId)
    expect(data.album.postCount).toBe(3)
    expect(dayjs(data.album.postsLastUpdatedAt) - dayjs(album.postsLastUpdatedAt)).toBeGreaterThan(0)
    expect(data.album.posts.items).toHaveLength(3)
    expect(data.album.posts.items[0].postId).toBe(postId3)
    expect(data.album.posts.items[1].postId).toBe(postId1)
    expect(data.album.posts.items[2].postId).toBe(postId2)
    // verify the art urls changed
    expect(data.album.art.url.split('?')[0]).not.toBe(album.art.url.split('?')[0])
    expect(data.album.art.url4k.split('?')[0]).not.toBe(album.art.url4k.split('?')[0])
    expect(data.album.art.url1080p.split('?')[0]).not.toBe(album.art.url1080p.split('?')[0])
    expect(data.album.art.url480p.split('?')[0]).not.toBe(album.art.url480p.split('?')[0])
    expect(data.album.art.url64p.split('?')[0]).not.toBe(album.art.url64p.split('?')[0])
    return data.album
  })

  // move the posts around a bit
  variables = {postId: postId2, precedingPostId: postId3}
  resp = await ourClient.mutate({mutation: mutations.editPostAlbumOrder, variables})
  expect(resp.data.editPostAlbumOrder.postId).toBe(postId2)

  // check album post order
  album = await eventually(async () => {
    const {data} = await ourClient.query({query: queries.album, variables: {albumId}})
    expect(data.album.albumId).toBe(albumId)
    expect(data.album.postCount).toBe(3)
    expect(dayjs(data.album.postsLastUpdatedAt) - dayjs(album.postsLastUpdatedAt)).toBeGreaterThan(0)
    expect(data.album.posts.items).toHaveLength(3)
    expect(data.album.posts.items[0].postId).toBe(postId3)
    expect(data.album.posts.items[1].postId).toBe(postId2)
    expect(data.album.posts.items[2].postId).toBe(postId1)
    // verify the art url have *not* changed - as first post didn't change
    expect(data.album.art.url.split('?')[0]).toBe(album.art.url.split('?')[0])
    expect(data.album.art.url4k.split('?')[0]).toBe(album.art.url4k.split('?')[0])
    expect(data.album.art.url1080p.split('?')[0]).toBe(album.art.url1080p.split('?')[0])
    expect(data.album.art.url480p.split('?')[0]).toBe(album.art.url480p.split('?')[0])
    expect(data.album.art.url64p.split('?')[0]).toBe(album.art.url64p.split('?')[0])
    return data.album
  })

  // move the posts around a bit
  variables = {postId: postId1}
  resp = await ourClient.mutate({mutation: mutations.editPostAlbumOrder, variables})
  expect(resp.data.editPostAlbumOrder.postId).toBe(postId1)

  // check album post order
  album = await eventually(async () => {
    const {data} = await ourClient.query({query: queries.album, variables: {albumId}})
    expect(data.album.albumId).toBe(albumId)
    expect(data.album.postCount).toBe(3)
    expect(dayjs(data.album.postsLastUpdatedAt) - dayjs(album.postsLastUpdatedAt)).toBeGreaterThan(0)
    expect(data.album.posts.items).toHaveLength(3)
    expect(data.album.posts.items[0].postId).toBe(postId1)
    expect(data.album.posts.items[1].postId).toBe(postId3)
    expect(data.album.posts.items[2].postId).toBe(postId2)
    // verify the art urls changed again
    expect(data.album.art.url.split('?')[0]).not.toBe(album.art.url.split('?')[0])
    expect(data.album.art.url4k.split('?')[0]).not.toBe(album.art.url4k.split('?')[0])
    expect(data.album.art.url1080p.split('?')[0]).not.toBe(album.art.url1080p.split('?')[0])
    expect(data.album.art.url480p.split('?')[0]).not.toBe(album.art.url480p.split('?')[0])
    expect(data.album.art.url64p.split('?')[0]).not.toBe(album.art.url64p.split('?')[0])
    return data.album
  })

  // try a no-op
  variables = {postId: postId3, precedingPostId: postId1}
  resp = await ourClient.mutate({mutation: mutations.editPostAlbumOrder, variables})
  expect(resp.data.editPostAlbumOrder.postId).toBe(postId3)

  // check album again directly, make sure nothing changed
  await sleep()
  await ourClient.query({query: queries.album, variables: {albumId}}).then(({data}) => {
    expect(data.album.albumId).toBe(albumId)
    expect(data.album.postCount).toBe(3)
    expect(data.album.postsLastUpdatedAt).toBe(album.postsLastUpdatedAt)
    expect(data.album.posts.items).toHaveLength(3)
    expect(data.album.posts.items[0].postId).toBe(postId1)
    expect(data.album.posts.items[1].postId).toBe(postId3)
    expect(data.album.posts.items[2].postId).toBe(postId2)
    // verify the art urls have *not* changed
    expect(data.album.art.url.split('?')[0]).toBe(album.art.url.split('?')[0])
    expect(data.album.art.url4k.split('?')[0]).toBe(album.art.url4k.split('?')[0])
    expect(data.album.art.url1080p.split('?')[0]).toBe(album.art.url1080p.split('?')[0])
    expect(data.album.art.url480p.split('?')[0]).toBe(album.art.url480p.split('?')[0])
    expect(data.album.art.url64p.split('?')[0]).toBe(album.art.url64p.split('?')[0])
  })
})

test('Cannot edit post album if we are disabled', async () => {
  const {client: ourClient, userId: ourUserId} = await loginCache.getCleanLogin()

  // we add an album
  const albumId = uuidv4()
  let resp = await ourClient.mutate({mutation: mutations.addAlbum, variables: {albumId, name: 'n1'}})
  expect(resp.data.addAlbum.albumId).toBe(albumId)

  // we add a post in that album
  const postId = uuidv4()
  resp = await ourClient.mutate({mutation: mutations.addPost, variables: {postId, imageData, albumId}})
  expect(resp.data.addPost.postId).toBe(postId)
  expect(resp.data.addPost.album.albumId).toBe(albumId)

  // we another post in that album
  const postId2 = uuidv4()
  resp = await ourClient.mutate({mutation: mutations.addPost, variables: {postId: postId2, imageData, albumId}})
  expect(resp.data.addPost.postId).toBe(postId2)
  expect(resp.data.addPost.album.albumId).toBe(albumId)

  // disable ourselves
  resp = await ourClient.mutate({mutation: mutations.disableUser})
  expect(resp.data.disableUser.userId).toBe(ourUserId)
  expect(resp.data.disableUser.userStatus).toBe('DISABLED')

  // verify we can't edit the album in that post
  await expect(
    ourClient.mutate({mutation: mutations.editPostAlbum, variables: {postId, albumId: ''}}),
  ).rejects.toThrow(/ClientError: User .* is not ACTIVE/)

  // verify we can't edit the order of psots in that album
  let variables = {postId: postId, precedingPostId: postId2}
  await expect(ourClient.mutate({mutation: mutations.editPostAlbumOrder, variables})).rejects.toThrow(
    /ClientError: User .* is not ACTIVE/,
  )
})
