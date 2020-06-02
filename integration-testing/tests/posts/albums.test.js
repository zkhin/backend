/* eslint-env jest */

const moment = require('moment')
const rp = require('request-promise-native')
const uuidv4 = require('uuid/v4')

const cognito = require('../../utils/cognito.js')
const misc = require('../../utils/misc.js')
const {mutations, queries} = require('../../schema')

const imageBytes = misc.generateRandomJpeg(8, 8)
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
  const [ourClient] = await loginCache.getCleanLogin()

  // we add an album
  const albumId = uuidv4()
  let resp = await ourClient.mutate({mutation: mutations.addAlbum, variables: {albumId, name: 'n'}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addAlbum.albumId).toBe(albumId)
  expect(resp.data.addAlbum.postCount).toBe(0)
  expect(resp.data.addAlbum.postsLastUpdatedAt).toBeNull()
  expect(resp.data.addAlbum.posts.items).toHaveLength(0)

  // we add an image post in that album
  const postId1 = uuidv4()
  let variables = {postId: postId1, albumId, imageData}
  resp = await ourClient.mutate({mutation: mutations.addPost, variables})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addPost.postId).toBe(postId1)
  let postedAt = resp.data.addPost.postedAt

  // check the album
  resp = await ourClient.query({query: queries.album, variables: {albumId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.album.albumId).toBe(albumId)
  expect(resp.data.album.postCount).toBe(1)
  expect(resp.data.album.postsLastUpdatedAt).toBe(postedAt)
  expect(resp.data.album.posts.items).toHaveLength(1)
  expect(resp.data.album.posts.items[0].postId).toBe(postId1)

  // we add another image post in that album, this one via cloudfront upload
  const postId2 = uuidv4()
  variables = {postId: postId2, albumId}
  resp = await ourClient.mutate({mutation: mutations.addPost, variables})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addPost.postId).toBe(postId2)
  let uploadUrl = resp.data.addPost.imageUploadUrl
  let before = moment().toISOString()
  await rp.put({url: uploadUrl, headers: imageHeaders, body: imageBytes})
  await misc.sleepUntilPostCompleted(ourClient, postId2)
  let after = moment().toISOString()

  // check the album
  resp = await ourClient.query({query: queries.album, variables: {albumId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.album.albumId).toBe(albumId)
  expect(resp.data.album.postCount).toBe(2)
  expect(before <= resp.data.album.postsLastUpdatedAt).toBe(true)
  expect(after >= resp.data.album.postsLastUpdatedAt).toBe(true)
  expect(resp.data.album.posts.items).toHaveLength(2)
  expect(resp.data.album.posts.items[0].postId).toBe(postId1)
  expect(resp.data.album.posts.items[1].postId).toBe(postId2)

  // we a text-only post in that album
  const postId3 = uuidv4()
  variables = {postId: postId3, albumId, text: 'lore ipsum', postType: 'TEXT_ONLY'}
  resp = await ourClient.mutate({mutation: mutations.addPost, variables})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addPost.postId).toBe(postId3)

  // check the album
  resp = await ourClient.query({query: queries.album, variables: {albumId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.album.albumId).toBe(albumId)
  expect(resp.data.album.postCount).toBe(3)
  expect(resp.data.album.posts.items).toHaveLength(3)
  expect(resp.data.album.posts.items[0].postId).toBe(postId1)
  expect(resp.data.album.posts.items[1].postId).toBe(postId2)
  expect(resp.data.album.posts.items[2].postId).toBe(postId3)
})

test('Cant create post in or move post into album that doesnt exist', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const albumId = uuidv4() // doesn't exist

  // verify we cannot create a post in that album
  const postId = uuidv4()
  let variables = {postId, albumId}
  await expect(ourClient.mutate({mutation: mutations.addPost, variables})).rejects.toThrow(
    /ClientError: Album .* does not exist/,
  )

  // make sure that post did not end making it into the DB
  let resp = await ourClient.query({query: queries.post, variables: {postId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.post).toBeNull()

  // we create a post, not in any album
  resp = await ourClient.mutate({mutation: mutations.addPost, variables: {postId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addPost.postId).toBe(postId)
  expect(resp.data.addPost.album).toBeNull()

  // verify neither we or them cannot move into no album
  variables = {postId, albumId}
  await expect(ourClient.mutate({mutation: mutations.editPostAlbum, variables})).rejects.toThrow(
    /ClientError: Album .* does not exist/,
  )

  // verify the post is unchanged
  resp = await ourClient.query({query: queries.post, variables: {postId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.post.postId).toBe(postId)
  expect(resp.data.post.album).toBeNull()
})

test('Cant create post in or move post into an album thats not ours', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()

  // they create an album
  const albumId = uuidv4()
  let resp = await theirClient.mutate({mutation: mutations.addAlbum, variables: {albumId, name: 'n1'}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addAlbum.albumId).toBe(albumId)

  // verify we cannot create a post in their album
  const postId = uuidv4()
  let variables = {postId, albumId}
  await expect(ourClient.mutate({mutation: mutations.addPost, variables})).rejects.toThrow(
    /ClientError: Album .* does not belong to caller /,
  )

  // make sure that post did not end making it into the DB
  resp = await theirClient.query({query: queries.post, variables: {postId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.post).toBeNull()

  // we create a post, not in any album
  resp = await ourClient.mutate({mutation: mutations.addPost, variables: {postId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addPost.postId).toBe(postId)
  expect(resp.data.addPost.album).toBeNull()
  let uploadUrl = resp.data.addPost.imageUploadUrl
  await rp.put({url: uploadUrl, headers: imageHeaders, body: imageBytes})
  await misc.sleepUntilPostCompleted(ourClient, postId)

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
  expect(resp.errors).toBeUndefined()
  expect(resp.data.post.postId).toBe(postId)
  expect(resp.data.post.album).toBeNull()
})

test('Adding a post with PENDING status does not affect Album.posts until COMPLETED', async () => {
  const [ourClient] = await loginCache.getCleanLogin()

  // we add an album
  const albumId = uuidv4()
  let resp = await ourClient.mutate({mutation: mutations.addAlbum, variables: {albumId, name: 'n'}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addAlbum.albumId).toBe(albumId)
  expect(resp.data.addAlbum.postCount).toBe(0)
  expect(resp.data.addAlbum.postsLastUpdatedAt).toBeNull()
  expect(resp.data.addAlbum.posts.items).toHaveLength(0)

  // we add a image post in that album (in PENDING state)
  const postId = uuidv4()
  resp = await ourClient.mutate({mutation: mutations.addPost, variables: {postId, albumId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addPost.postId).toBe(postId)
  expect(resp.data.addPost.postStatus).toBe('PENDING')
  expect(resp.data.addPost.album.albumId).toBe(albumId)
  const uploadUrl = resp.data.addPost.imageUploadUrl

  // check the album's posts, should not see the new post
  resp = await ourClient.query({query: queries.album, variables: {albumId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.album.albumId).toBe(albumId)
  expect(resp.data.album.postCount).toBe(0)
  expect(resp.data.album.postsLastUpdatedAt).toBeNull()
  expect(resp.data.album.posts.items).toHaveLength(0)

  // upload the image, thus completing the post
  await rp.put({url: uploadUrl, headers: imageHeaders, body: imageBytes})
  await misc.sleepUntilPostCompleted(ourClient, postId)

  // verify the post is now COMPLETED
  resp = await ourClient.query({query: queries.post, variables: {postId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.post.postId).toBe(postId)
  expect(resp.data.post.postStatus).toBe('COMPLETED')

  // check the album's posts, *should* see the new post
  resp = await ourClient.query({query: queries.album, variables: {albumId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.album.albumId).toBe(albumId)
  expect(resp.data.album.postCount).toBe(1)
  expect(resp.data.album.postsLastUpdatedAt).toBeTruthy()
  expect(resp.data.album.posts.items).toHaveLength(1)
  expect(resp.data.album.posts.items[0].postId).toBe(postId)
})

test('Add, remove, change albums for an existing post', async () => {
  const [ourClient] = await loginCache.getCleanLogin()

  // add two albums
  const [albumId1, albumId2] = [uuidv4(), uuidv4()]
  let resp = await ourClient.mutate({mutation: mutations.addAlbum, variables: {albumId: albumId1, name: 'n1'}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addAlbum.albumId).toBe(albumId1)
  resp = await ourClient.mutate({mutation: mutations.addAlbum, variables: {albumId: albumId2, name: 'n2'}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addAlbum.albumId).toBe(albumId2)

  // add a post, not in any album
  const postId = uuidv4()
  resp = await ourClient.mutate({mutation: mutations.addPost, variables: {postId, imageData}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addPost.postId).toBe(postId)
  expect(resp.data.addPost.postStatus).toBe('COMPLETED')
  expect(resp.data.addPost.album).toBeNull()

  // move that post into the 2nd album
  let before = moment().toISOString()
  resp = await ourClient.mutate({mutation: mutations.editPostAlbum, variables: {postId, albumId: albumId2}})
  let after = moment().toISOString()
  expect(resp.errors).toBeUndefined()
  expect(resp.data.editPostAlbum.postId).toBe(postId)
  expect(resp.data.editPostAlbum.album.albumId).toBe(albumId2)

  // check the second album
  resp = await ourClient.query({query: queries.album, variables: {albumId: albumId2}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.album.albumId).toBe(albumId2)
  expect(resp.data.album.postCount).toBe(1)
  expect(resp.data.album.posts.items).toHaveLength(1)
  expect(resp.data.album.posts.items[0].postId).toBe(postId)
  expect(before <= resp.data.album.postsLastUpdatedAt).toBe(true)
  expect(after >= resp.data.album.postsLastUpdatedAt).toBe(true)

  // add an unrelated text-only post to the first album
  const postId2 = uuidv4()
  let variables = {postId: postId2, albumId: albumId1, text: 'lore ipsum', postType: 'TEXT_ONLY'}
  resp = await ourClient.mutate({mutation: mutations.addPost, variables})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addPost.postId).toBe(postId2)
  expect(resp.data.addPost.postStatus).toBe('COMPLETED')
  expect(resp.data.addPost.album.albumId).toBe(albumId1)

  // move the original post out of the 2nd album and into the first
  before = moment().toISOString()
  resp = await ourClient.mutate({mutation: mutations.editPostAlbum, variables: {postId, albumId: albumId1}})
  after = moment().toISOString()
  expect(resp.errors).toBeUndefined()
  expect(resp.data.editPostAlbum.postId).toBe(postId)
  expect(resp.data.editPostAlbum.album.albumId).toBe(albumId1)

  // check the 2nd album
  resp = await ourClient.query({query: queries.album, variables: {albumId: albumId2}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.album.albumId).toBe(albumId2)
  expect(resp.data.album.postCount).toBe(0)
  expect(resp.data.album.posts.items).toHaveLength(0)
  expect(before <= resp.data.album.postsLastUpdatedAt).toBe(true)
  expect(after >= resp.data.album.postsLastUpdatedAt).toBe(true)

  // check the first album, including post order - new post should be at the back
  resp = await ourClient.query({query: queries.album, variables: {albumId: albumId1}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.album.albumId).toBe(albumId1)
  expect(resp.data.album.postCount).toBe(2)
  expect(resp.data.album.posts.items).toHaveLength(2)
  expect(resp.data.album.posts.items[0].postId).toBe(postId2)
  expect(resp.data.album.posts.items[1].postId).toBe(postId)
  expect(before <= resp.data.album.postsLastUpdatedAt).toBe(true)
  expect(after >= resp.data.album.postsLastUpdatedAt).toBe(true)

  // remove the post from that album
  before = moment().toISOString()
  resp = await ourClient.mutate({mutation: mutations.editPostAlbum, variables: {postId, albumId: null}})
  after = moment().toISOString()
  expect(resp.errors).toBeUndefined()
  expect(resp.data.editPostAlbum.postId).toBe(postId)
  expect(resp.data.editPostAlbum.album).toBeNull()

  // check the first album
  resp = await ourClient.query({query: queries.album, variables: {albumId: albumId1}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.album.albumId).toBe(albumId1)
  expect(resp.data.album.postCount).toBe(1)
  expect(resp.data.album.posts.items).toHaveLength(1)
  expect(resp.data.album.posts.items[0].postId).toBe(postId2)
  expect(before <= resp.data.album.postsLastUpdatedAt).toBe(true)
  expect(after >= resp.data.album.postsLastUpdatedAt).toBe(true)
})

// TODO: define behavior here. It's probably ok to let vido posts into albums, as they now have 'poster' images
test.skip('Cant add video post to album (yet)', async () => {
  const [ourClient] = await loginCache.getCleanLogin()

  // add an albums
  const albumId = uuidv4()
  let resp = await ourClient.mutate({mutation: mutations.addAlbum, variables: {albumId: albumId, name: 'n1'}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addAlbum.albumId).toBe(albumId)

  // verify can't create video post in that album
  const postId = uuidv4()
  await expect(
    ourClient.mutate({mutation: mutations.addPost, variables: {postId, postType: 'VIDEO', albumId}}),
  ).rejects.toThrow('ClientError lsadfkjasldkfj')

  // create the video post
  resp = ourClient.mutate({mutation: mutations.addPost, variables: {postId, postType: 'VIDEO'}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addPost.postId).toBe(postId)

  // verify can't move the video post into that album
  await expect(ourClient.mutate({mutation: mutations.editPostAlbum, variables: {postId, albumId}})).rejects.toThrow(
    'ClientError lsadfkjasldkfj',
  )
})

test('Adding an existing post to album not in COMPLETED status has no affect on Album.post & friends', async () => {
  const [ourClient] = await loginCache.getCleanLogin()

  // add an albums
  const albumId = uuidv4()
  let resp = await ourClient.mutate({mutation: mutations.addAlbum, variables: {albumId, name: 'n1'}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addAlbum.albumId).toBe(albumId)

  // add an image post, leave it in PENDING state
  const postId1 = uuidv4()
  resp = await ourClient.mutate({mutation: mutations.addPost, variables: {postId: postId1}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addPost.postId).toBe(postId1)
  expect(resp.data.addPost.postStatus).toBe('PENDING')

  // add an image post, and archive it
  const postId2 = uuidv4()
  let variables = {postId: postId2, imageData}
  resp = await ourClient.mutate({mutation: mutations.addPost, variables})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addPost.postId).toBe(postId2)
  resp = await ourClient.mutate({mutation: mutations.archivePost, variables: {postId: postId2}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.archivePost.postId).toBe(postId2)
  expect(resp.data.archivePost.postStatus).toBe('ARCHIVED')

  // add post the PENDING and the ARCHIVED posts to the album
  resp = await ourClient.mutate({mutation: mutations.editPostAlbum, variables: {postId: postId1, albumId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.editPostAlbum.postId).toBe(postId1)
  expect(resp.data.editPostAlbum.album.albumId).toBe(albumId)
  resp = await ourClient.mutate({mutation: mutations.editPostAlbum, variables: {postId: postId2, albumId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.editPostAlbum.postId).toBe(postId2)
  expect(resp.data.editPostAlbum.album.albumId).toBe(albumId)

  // check that Album.posts & friends have not changed
  resp = await ourClient.query({query: queries.album, variables: {albumId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.album.albumId).toBe(albumId)
  expect(resp.data.album.postCount).toBe(0)
  expect(resp.data.album.postsLastUpdatedAt).toBeNull()
  expect(resp.data.album.posts.items).toHaveLength(0)
})

test('Archiving a post removes it from Album.posts & friends, restoring it does not maintain rank', async () => {
  const [ourClient] = await loginCache.getCleanLogin()

  // add an album
  const albumId = uuidv4()
  let resp = await ourClient.mutate({mutation: mutations.addAlbum, variables: {albumId, name: 'n1'}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addAlbum.albumId).toBe(albumId)

  // add an image post in the album
  const postId = uuidv4()
  let variables = {postId, albumId, imageData}
  resp = await ourClient.mutate({mutation: mutations.addPost, variables})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addPost.postId).toBe(postId)
  expect(resp.data.addPost.postStatus).toBe('COMPLETED')
  expect(resp.data.addPost.album.albumId).toBe(albumId)
  await misc.sleep(1000) // let dynamo converge

  // add another image post in the album
  const postId2 = uuidv4()
  variables = {postId: postId2, albumId, imageData}
  resp = await ourClient.mutate({mutation: mutations.addPost, variables})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addPost.postId).toBe(postId2)
  expect(resp.data.addPost.postStatus).toBe('COMPLETED')
  expect(resp.data.addPost.album.albumId).toBe(albumId)

  // verify that's reflected in Album.posts and friends
  resp = await ourClient.query({query: queries.album, variables: {albumId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.album.albumId).toBe(albumId)
  expect(resp.data.album.postCount).toBe(2)
  expect(resp.data.album.posts.items).toHaveLength(2)
  expect(resp.data.album.posts.items[0].postId).toBe(postId)
  expect(resp.data.album.posts.items[1].postId).toBe(postId2)
  let postsLastUpdatedAt = resp.data.album.postsLastUpdatedAt
  expect(postsLastUpdatedAt).toBeTruthy()

  // archive the post
  resp = await ourClient.mutate({mutation: mutations.archivePost, variables: {postId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.archivePost.postId).toBe(postId)
  expect(resp.data.archivePost.postStatus).toBe('ARCHIVED')

  // verify that took it out of Album.post and friends
  resp = await ourClient.query({query: queries.album, variables: {albumId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.album.albumId).toBe(albumId)
  expect(resp.data.album.postCount).toBe(1)
  expect(resp.data.album.posts.items).toHaveLength(1)
  expect(resp.data.album.posts.items[0].postId).toBe(postId2)
  expect(resp.data.album.postsLastUpdatedAt > postsLastUpdatedAt).toBe(true)
  postsLastUpdatedAt = resp.data.album.postsLastUpdatedAt

  // restore the post
  resp = await ourClient.mutate({mutation: mutations.restoreArchivedPost, variables: {postId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.restoreArchivedPost.postId).toBe(postId)
  expect(resp.data.restoreArchivedPost.postStatus).toBe('COMPLETED')

  // verify its now back in Album.posts and friends, in the back
  resp = await ourClient.query({query: queries.album, variables: {albumId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.album.albumId).toBe(albumId)
  expect(resp.data.album.postCount).toBe(2)
  expect(resp.data.album.posts.items).toHaveLength(2)
  expect(resp.data.album.posts.items[0].postId).toBe(postId2)
  expect(resp.data.album.posts.items[1].postId).toBe(postId)
  expect(resp.data.album.postsLastUpdatedAt > postsLastUpdatedAt).toBe(true)
})

test('Deleting a post removes it from Album.posts & friends', async () => {
  const [ourClient] = await loginCache.getCleanLogin()

  // add an albums
  const albumId = uuidv4()
  let resp = await ourClient.mutate({mutation: mutations.addAlbum, variables: {albumId, name: 'n1'}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addAlbum.albumId).toBe(albumId)

  // add an image post in the album
  const postId = uuidv4()
  let variables = {postId, albumId, imageData}
  resp = await ourClient.mutate({mutation: mutations.addPost, variables})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addPost.postId).toBe(postId)
  expect(resp.data.addPost.postStatus).toBe('COMPLETED')
  expect(resp.data.addPost.album.albumId).toBe(albumId)

  // verify that's reflected in Album.posts and friends
  resp = await ourClient.query({query: queries.album, variables: {albumId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.album.albumId).toBe(albumId)
  expect(resp.data.album.postCount).toBe(1)
  expect(resp.data.album.posts.items).toHaveLength(1)
  expect(resp.data.album.posts.items[0].postId).toBe(postId)
  let postsLastUpdatedAt = resp.data.album.postsLastUpdatedAt
  expect(postsLastUpdatedAt).toBeTruthy()

  // delete the post
  resp = await ourClient.mutate({mutation: mutations.deletePost, variables: {postId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.deletePost.postId).toBe(postId)
  expect(resp.data.deletePost.postStatus).toBe('DELETING')

  // verify that took it out of Album.post and friends
  resp = await ourClient.query({query: queries.album, variables: {albumId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.album.albumId).toBe(albumId)
  expect(resp.data.album.postCount).toBe(0)
  expect(resp.data.album.posts.items).toHaveLength(0)
  expect(postsLastUpdatedAt < resp.data.album.postsLastUpdatedAt).toBe(true)
})

test('Edit album post order failures', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()
  const [albumId, albumId2, postId1, postId2, postId3] = [uuidv4(), uuidv4(), uuidv4(), uuidv4(), uuidv4()]

  // we add an album
  let variables = {albumId, name: 'n1'}
  let resp = await ourClient.mutate({mutation: mutations.addAlbum, variables})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addAlbum.albumId).toBe(albumId)

  // they add nother album
  variables = {albumId: albumId2, name: 'n2'}
  resp = await theirClient.mutate({mutation: mutations.addAlbum, variables})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addAlbum.albumId).toBe(albumId2)

  // we add two posts to the album
  variables = {postId: postId1, albumId, imageData}
  resp = await ourClient.mutate({mutation: mutations.addPost, variables})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addPost.postId).toBe(postId1)

  variables = {postId: postId2, albumId, imageData}
  resp = await ourClient.mutate({mutation: mutations.addPost, variables})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addPost.postId).toBe(postId2)

  // they add a post, in a different album
  variables = {postId: postId3, imageData, albumId: albumId2}
  resp = await theirClient.mutate({mutation: mutations.addPost, variables})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addPost.postId).toBe(postId3)

  // check album post order
  resp = await ourClient.query({query: queries.album, variables: {albumId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.album.albumId).toBe(albumId)
  expect(resp.data.album.postCount).toBe(2)
  expect(resp.data.album.posts.items).toHaveLength(2)
  expect(resp.data.album.posts.items[0].postId).toBe(postId1)
  expect(resp.data.album.posts.items[1].postId).toBe(postId2)

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
  resp = await ourClient.query({query: queries.album, variables: {albumId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.album.albumId).toBe(albumId)
  expect(resp.data.album.postCount).toBe(2)
  expect(resp.data.album.posts.items).toHaveLength(2)
  expect(resp.data.album.posts.items[0].postId).toBe(postId1)
  expect(resp.data.album.posts.items[1].postId).toBe(postId2)

  // make sure post change order can actually complete without error
  variables = {postId: postId1, precedingPostId: postId2}
  resp = await ourClient.mutate({mutation: mutations.editPostAlbumOrder, variables})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.editPostAlbumOrder.postId).toBe(postId1)
  expect(resp.data.editPostAlbumOrder.album.albumId).toBe(albumId)
})

test('Edit album post order', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const [albumId, postId1, postId2, postId3] = [uuidv4(), uuidv4(), uuidv4(), uuidv4()]

  // we add an album
  let variables = {albumId, name: 'n1'}
  let resp = await ourClient.mutate({mutation: mutations.addAlbum, variables})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addAlbum.albumId).toBe(albumId)

  // we add three posts to the album
  variables = {postId: postId1, albumId, text: 'lore', postType: 'TEXT_ONLY'}
  resp = await ourClient.mutate({mutation: mutations.addPost, variables})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addPost.postId).toBe(postId1)

  variables = {postId: postId2, albumId, imageData}
  resp = await ourClient.mutate({mutation: mutations.addPost, variables})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addPost.postId).toBe(postId2)

  variables = {postId: postId3, albumId, text: 'ipsum', postType: 'TEXT_ONLY'}
  resp = await ourClient.mutate({mutation: mutations.addPost, variables})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addPost.postId).toBe(postId3)

  // check album post order
  resp = await ourClient.query({query: queries.album, variables: {albumId}})
  expect(resp.errors).toBeUndefined()
  let album = resp.data.album
  expect(album.albumId).toBe(albumId)
  expect(album.postCount).toBe(3)
  expect(album.posts.items).toHaveLength(3)
  expect(album.posts.items[0].postId).toBe(postId1)
  expect(album.posts.items[1].postId).toBe(postId2)
  expect(album.posts.items[2].postId).toBe(postId3)
  let prevAlbum = album

  // move the posts around a bit
  variables = {postId: postId3, precedingPostId: null}
  resp = await ourClient.mutate({mutation: mutations.editPostAlbumOrder, variables})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.editPostAlbumOrder.postId).toBe(postId3)
  await misc.sleep(2000) // let dynamo converge

  // check album post order
  resp = await ourClient.query({query: queries.album, variables: {albumId}})
  expect(resp.errors).toBeUndefined()
  album = resp.data.album
  expect(album.albumId).toBe(albumId)
  expect(album.postCount).toBe(3)
  expect(album.posts.items).toHaveLength(3)
  expect(album.posts.items[0].postId).toBe(postId3)
  expect(album.posts.items[1].postId).toBe(postId1)
  expect(album.posts.items[2].postId).toBe(postId2)

  // verify the art urls changed
  expect(prevAlbum.art.url.split('?')[0]).not.toBe(album.art.url.split('?')[0])
  expect(prevAlbum.art.url4k.split('?')[0]).not.toBe(album.art.url4k.split('?')[0])
  expect(prevAlbum.art.url1080p.split('?')[0]).not.toBe(album.art.url1080p.split('?')[0])
  expect(prevAlbum.art.url480p.split('?')[0]).not.toBe(album.art.url480p.split('?')[0])
  expect(prevAlbum.art.url64p.split('?')[0]).not.toBe(album.art.url64p.split('?')[0])
  prevAlbum = album

  // move the posts around a bit
  variables = {postId: postId2, precedingPostId: postId3}
  resp = await ourClient.mutate({mutation: mutations.editPostAlbumOrder, variables})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.editPostAlbumOrder.postId).toBe(postId2)
  await misc.sleep(2000) // let dynamo converge

  // check album post order
  resp = await ourClient.query({query: queries.album, variables: {albumId}})
  expect(resp.errors).toBeUndefined()
  album = resp.data.album
  expect(album.albumId).toBe(albumId)
  expect(album.postCount).toBe(3)
  expect(album.posts.items).toHaveLength(3)
  expect(album.posts.items[0].postId).toBe(postId3)
  expect(album.posts.items[1].postId).toBe(postId2)
  expect(album.posts.items[2].postId).toBe(postId1)

  // verify the art url have *not* changed - as first post didn't change
  expect(prevAlbum.art.url.split('?')[0]).toBe(album.art.url.split('?')[0])
  expect(prevAlbum.art.url4k.split('?')[0]).toBe(album.art.url4k.split('?')[0])
  expect(prevAlbum.art.url1080p.split('?')[0]).toBe(album.art.url1080p.split('?')[0])
  expect(prevAlbum.art.url480p.split('?')[0]).toBe(album.art.url480p.split('?')[0])
  expect(prevAlbum.art.url64p.split('?')[0]).toBe(album.art.url64p.split('?')[0])
  prevAlbum = album

  // move the posts around a bit
  variables = {postId: postId1}
  resp = await ourClient.mutate({mutation: mutations.editPostAlbumOrder, variables})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.editPostAlbumOrder.postId).toBe(postId1)
  await misc.sleep(2000) // let dynamo converge

  // check album post order
  resp = await ourClient.query({query: queries.album, variables: {albumId}})
  expect(resp.errors).toBeUndefined()
  album = resp.data.album
  expect(album.albumId).toBe(albumId)
  expect(album.postCount).toBe(3)
  expect(album.posts.items).toHaveLength(3)
  expect(album.posts.items[0].postId).toBe(postId1)
  expect(album.posts.items[1].postId).toBe(postId3)
  expect(album.posts.items[2].postId).toBe(postId2)

  // verify the art urls changed again
  expect(prevAlbum.art.url.split('?')[0]).not.toBe(album.art.url.split('?')[0])
  expect(prevAlbum.art.url4k.split('?')[0]).not.toBe(album.art.url4k.split('?')[0])
  expect(prevAlbum.art.url1080p.split('?')[0]).not.toBe(album.art.url1080p.split('?')[0])
  expect(prevAlbum.art.url480p.split('?')[0]).not.toBe(album.art.url480p.split('?')[0])
  expect(prevAlbum.art.url64p.split('?')[0]).not.toBe(album.art.url64p.split('?')[0])
  prevAlbum = album

  // try a no-op
  variables = {postId: postId3, precedingPostId: postId1}
  resp = await ourClient.mutate({mutation: mutations.editPostAlbumOrder, variables})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.editPostAlbumOrder.postId).toBe(postId3)
  await misc.sleep(2000) // let dynamo converge

  // check album again directly, make sure nothing changed
  resp = await ourClient.query({query: queries.album, variables: {albumId}})
  expect(resp.errors).toBeUndefined()
  album = resp.data.album
  expect(album.albumId).toBe(albumId)
  expect(album.postCount).toBe(3)
  expect(album.posts.items).toHaveLength(3)
  expect(album.posts.items[0].postId).toBe(postId1)
  expect(album.posts.items[1].postId).toBe(postId3)
  expect(album.posts.items[2].postId).toBe(postId2)

  // verify the art urls have *not* changed
  expect(prevAlbum.art.url.split('?')[0]).toBe(album.art.url.split('?')[0])
  expect(prevAlbum.art.url4k.split('?')[0]).toBe(album.art.url4k.split('?')[0])
  expect(prevAlbum.art.url1080p.split('?')[0]).toBe(album.art.url1080p.split('?')[0])
  expect(prevAlbum.art.url480p.split('?')[0]).toBe(album.art.url480p.split('?')[0])
  expect(prevAlbum.art.url64p.split('?')[0]).toBe(album.art.url64p.split('?')[0])
})

test('Cannot edit post album if we are disabled', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()

  // we add an album
  const albumId = uuidv4()
  let resp = await ourClient.mutate({mutation: mutations.addAlbum, variables: {albumId, name: 'n1'}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addAlbum.albumId).toBe(albumId)

  // we add a post in that album
  const postId = uuidv4()
  resp = await ourClient.mutate({mutation: mutations.addPost, variables: {postId, imageData, albumId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addPost.postId).toBe(postId)
  expect(resp.data.addPost.album.albumId).toBe(albumId)

  // we another post in that album
  const postId2 = uuidv4()
  resp = await ourClient.mutate({mutation: mutations.addPost, variables: {postId: postId2, imageData, albumId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addPost.postId).toBe(postId2)
  expect(resp.data.addPost.album.albumId).toBe(albumId)

  // disable ourselves
  resp = await ourClient.mutate({mutation: mutations.disableUser})
  expect(resp.errors).toBeUndefined()
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
