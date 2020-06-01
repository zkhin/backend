/* eslint-env jest */

const moment = require('moment')
const rp = require('request-promise-native')
const uuidv4 = require('uuid/v4')

const cognito = require('../utils/cognito.js')
const misc = require('../utils/misc.js')
const { mutations, queries } = require('../schema')

const imageBytes = misc.generateRandomJpeg(8, 8)
const imageData = new Buffer.from(imageBytes).toString('base64')

const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})

beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.reset())


test('Add, read, and delete an album', async () => {
  const [ourClient] = await loginCache.getCleanLogin()

  // we add an album with minimal options
  const albumId = uuidv4()
  const name = 'album name'
  const before = moment().toISOString()
  let resp = await ourClient.mutate({mutation: mutations.addAlbum, variables: {albumId, name}})
  const after = moment().toISOString()
  expect(resp.errors).toBeUndefined()
  const album = resp.data.addAlbum
  expect(album.albumId).toBe(albumId)
  expect(album.name).toBe(name)
  expect(album.description).toBeNull()
  expect(album.art.url).toBeTruthy()
  expect(album.art.url4k).toBeTruthy()
  expect(album.art.url1080p).toBeTruthy()
  expect(album.art.url480p).toBeTruthy()
  expect(album.art.url64p).toBeTruthy()
  expect(album.postCount).toBe(0)
  expect(album.postsLastUpdatedAt).toBeNull()
  expect(album.posts.items).toHaveLength(0)
  expect(before <= album.createdAt).toBe(true)
  expect(after >= album.createdAt).toBe(true)

  // read that album via direct access
  resp = await ourClient.query({query: queries.album, variables: {albumId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.album).toEqual(album)

  // delete the album
  resp = await ourClient.mutate({mutation: mutations.deleteAlbum, variables: {albumId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.deleteAlbum).toEqual(album)

  // check its really gone
  resp = await ourClient.query({query: queries.album, variables: {albumId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.album).toBeNull()
})


test('Cannot add, edit or delete an album if we are disabled', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()

  // we add an album with minimal options
  const albumId = uuidv4()
  let resp = await ourClient.mutate({mutation: mutations.addAlbum, variables: {albumId, name: 'n'}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addAlbum.albumId).toEqual(albumId)

  // we disable ourselves
  resp = await ourClient.mutate({mutation: mutations.disableUser})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.disableUser.userId).toBe(ourUserId)
  expect(resp.data.disableUser.userStatus).toBe('DISABLED')

  // verify we can't add another album
  await expect(ourClient.mutate({mutation: mutations.addAlbum, variables: {albumId: uuidv4(), name: 'n'}}))
    .rejects.toThrow(/ClientError: User .* is not ACTIVE/)

  // verify we can't edit or delete the existing album
  await expect(ourClient.mutate({mutation: mutations.editAlbum, variables: {albumId, name: 'new'}}))
    .rejects.toThrow(/ClientError: User .* is not ACTIVE/)
  await expect(ourClient.mutate({mutation: mutations.deleteAlbum, variables: {albumId}}))
    .rejects.toThrow(/ClientError: User .* is not ACTIVE/)
})


test('Add album with empty string description, treated as null', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const albumId = uuidv4()
  let resp = await ourClient.mutate({mutation: mutations.addAlbum, variables: {albumId, name: 'r', description: ''}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addAlbum.albumId).toBe(albumId)
  expect(resp.data.addAlbum.description).toBeNull()
})


test('Edit an album', async () => {
  const [ourClient] = await loginCache.getCleanLogin()

  // we add an album with maximal options
  const albumId = uuidv4()
  const orgName = 'org album name'
  const orgDescription = 'org album desc'
  let resp = await ourClient.mutate({
    mutation: mutations.addAlbum,
    variables: {albumId, name: orgName, description: orgDescription},
  })
  expect(resp.errors).toBeUndefined()
  const orgAlbum = resp.data.addAlbum
  expect(orgAlbum.albumId).toBe(albumId)
  expect(orgAlbum.name).toBe(orgName)
  expect(orgAlbum.description).toBe(orgDescription)

  // edit the options on that album
  const newName = 'new album name'
  const newDescription = 'new album desc'
  resp = await ourClient.mutate({
    mutation: mutations.editAlbum,
    variables: {albumId, name: newName, description: newDescription},
  })
  expect(resp.errors).toBeUndefined()
  const editedAlbum = resp.data.editAlbum
  expect(editedAlbum.albumId).toBe(albumId)
  expect(editedAlbum.name).toBe(newName)
  expect(editedAlbum.description).toBe(newDescription)
  expect({
    ...editedAlbum,
    ...{name: orgAlbum.name, description: orgAlbum.description}
  }).toEqual(orgAlbum)

  // verify those stuck in the DB
  resp = await ourClient.query({query: queries.album, variables: {albumId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.album).toEqual(editedAlbum)

  // delete the options which we can on that album, using empty string
  resp = await ourClient.mutate({mutation: mutations.editAlbum, variables: {albumId, description: ''}})
  expect(resp.errors).toBeUndefined()
  const clearedAlbum = resp.data.editAlbum
  expect(clearedAlbum.albumId).toBe(albumId)
  expect(clearedAlbum.name).toBe(newName)
  expect(clearedAlbum.description).toBeNull()
  expect({
    ...clearedAlbum,
    ...{description: editedAlbum.description}
  }).toEqual(editedAlbum)

  // verify those stuck in the DB
  resp = await ourClient.query({query: queries.album, variables: {albumId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.album).toEqual(clearedAlbum)

  // verify we can't null out the album name
  let variables = {albumId, name: ''}
  await expect(ourClient.mutate({mutation: mutations.editAlbum, variables}))
    .rejects.toThrow(/ClientError: All albums must have names/)
})


test('Cant create two albums with same id', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()

  // we add an album
  const albumId = uuidv4()
  let resp = await ourClient.mutate({mutation: mutations.addAlbum, variables: {albumId, name: 'n'}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addAlbum.albumId).toBe(albumId)

  // verify neither us nor them can add another album with same id
  let variables = {albumId, name: 'r'}
  await expect(ourClient.mutate({mutation: mutations.addAlbum, variables}))
    .rejects.toThrow(/ClientError: Unable to add album /)
  await expect(theirClient.mutate({mutation: mutations.addAlbum, variables}))
    .rejects.toThrow(/ClientError: Unable to add album /)
})


test('Cant edit or delete somebody elses album', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()

  // we add an album
  const albumId = uuidv4()
  let resp = await ourClient.mutate({mutation: mutations.addAlbum, variables: {albumId, name: 'n'}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addAlbum.albumId).toBe(albumId)

  // verify they can't edit it nor delete it
  let variables = {albumId, name: 'name'}
  await expect(theirClient.mutate({mutation: mutations.editAlbum, variables}))
    .rejects.toThrow(/ClientError: Caller .* does not own Album /)
  await expect(theirClient.mutate({mutation: mutations.deleteAlbum, variables}))
    .rejects.toThrow(/ClientError: Caller .* does not own Album /)

  // verify it's still there
  resp = await theirClient.query({query: queries.album, variables: {albumId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.album.albumId).toBe(albumId)
})


test('Empty album edit raises error', async () => {
  const [ourClient] = await loginCache.getCleanLogin()

  // we add an album
  const albumId = uuidv4()
  let resp = await ourClient.mutate({mutation: mutations.addAlbum, variables: {albumId, name: 'n'}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addAlbum.albumId).toBe(albumId)

  // verify calling edit without specifying anything to edit is an error
  await expect(ourClient.mutate({mutation: mutations.editAlbum, variables: {albumId}}))
    .rejects.toThrow(/ClientError: Called without any arguments/)
})


test('Cant edit, delete an album that doesnt exist', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const albumId = uuidv4()  // doesnt exist

  // cant edit or delete the non-existing album
  let variables = {albumId, name: 'name'}
  await expect(ourClient.mutate({mutation: mutations.editAlbum, variables}))
    .rejects.toThrow(/ClientError: Album .* does not exist/)
  await expect(ourClient.mutate({mutation: mutations.deleteAlbum, variables}))
    .rejects.toThrow(/ClientError: Album .* does not exist/)
})


test('User.albums and Query.album block privacy', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient, theirUserId] = await loginCache.getCleanLogin()

  // we add an album
  const albumId = uuidv4()
  let resp = await ourClient.mutate({mutation: mutations.addAlbum, variables: {albumId, name: 'n'}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addAlbum.albumId).toBe(albumId)

  // check they can see our albums
  resp = await theirClient.query({query: queries.user, variables: {userId: ourUserId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.user.albumCount).toBe(1)
  expect(resp.data.user.albums.items).toHaveLength(1)

  // check they can see the album directly
  resp = await theirClient.query({query: queries.album, variables: {albumId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.album.albumId).toBe(albumId)

  // we block them
  resp = await ourClient.mutate({mutation: mutations.blockUser, variables: {userId: theirUserId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.blockUser.userId).toBe(theirUserId)

  // check they cannot see our albums
  resp = await theirClient.query({query: queries.user, variables: {userId: ourUserId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.user.albumCount).toBeNull()
  expect(resp.data.user.albums).toBeNull()

  // check they cannot see the album directly
  resp = await theirClient.query({query: queries.album, variables: {albumId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.album).toBeNull()

  // we unblock them
  resp = await ourClient.mutate({mutation: mutations.unblockUser, variables: {userId: theirUserId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.unblockUser.userId).toBe(theirUserId)

  // check they can see our albums
  resp = await theirClient.query({query: queries.user, variables: {userId: ourUserId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.user.albumCount).toBe(1)
  expect(resp.data.user.albums.items).toHaveLength(1)

  // check they can see the album directly
  resp = await theirClient.query({query: queries.album, variables: {albumId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.album.albumId).toBe(albumId)
})


test('User.albums and Query.album private user privacy', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient, theirUserId] = await loginCache.getCleanLogin()

  // check they *can* see our albums
  let resp = await theirClient.query({query: queries.user, variables: {userId: ourUserId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.user.albumCount).toBe(0)
  expect(resp.data.user.albums.items).toHaveLength(0)

  // we go private
  resp = await ourClient.mutate({mutation: mutations.setUserPrivacyStatus, variables: {privacyStatus: 'PRIVATE'}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.setUserDetails.privacyStatus).toBe('PRIVATE')

  // we add an album
  const albumId = uuidv4()
  resp = await ourClient.mutate({mutation: mutations.addAlbum, variables: {albumId, name: 'n'}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addAlbum.albumId).toBe(albumId)

  // check they cannot see our albums
  resp = await theirClient.query({query: queries.user, variables: {userId: ourUserId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.user.albumCount).toBeNull()
  expect(resp.data.user.albums).toBeNull()

  // check they cannot see the album directly
  resp = await theirClient.query({query: queries.album, variables: {albumId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.album).toBeNull()

  // they request to follow us
  resp = await theirClient.mutate({mutation: mutations.followUser, variables: {userId: ourUserId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.followUser.followedStatus).toBe('REQUESTED')

  // check they cannot see our albums
  resp = await theirClient.query({query: queries.user, variables: {userId: ourUserId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.user.albumCount).toBeNull()
  expect(resp.data.user.albums).toBeNull()

  // check they cannot see the album directly
  resp = await theirClient.query({query: queries.album, variables: {albumId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.album).toBeNull()

  // we accept their follow request
  resp = await ourClient.mutate({mutation: mutations.acceptFollowerUser, variables: {userId: theirUserId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.acceptFollowerUser.followerStatus).toBe('FOLLOWING')

  // check they *can* see our albums
  resp = await theirClient.query({query: queries.user, variables: {userId: ourUserId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.user.albumCount).toBe(1)
  expect(resp.data.user.albums.items).toHaveLength(1)

  // check they *can* see the album directly
  resp = await theirClient.query({query: queries.album, variables: {albumId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.album.albumId).toBe(albumId)

  // now we deny their follow request
  resp = await ourClient.mutate({mutation: mutations.denyFollowerUser, variables: {userId: theirUserId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.denyFollowerUser.followerStatus).toBe('DENIED')

  // check they cannot see our albums
  resp = await theirClient.query({query: queries.user, variables: {userId: ourUserId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.user.albumCount).toBeNull()
  expect(resp.data.user.albums).toBeNull()

  // check they cannot see the album directly
  resp = await theirClient.query({query: queries.album, variables: {albumId}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.album).toBeNull()
})


test('User.albums matches direct access, ordering', async () => {
  const [ourClient] = await loginCache.getCleanLogin()

  // check we have no albums
  let resp = await ourClient.query({query: queries.self})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.self.albumCount).toBe(0)
  expect(resp.data.self.albums.items).toHaveLength(0)

  // we add two albums - one minimal one maximal
  const [albumId1, albumId2] = [uuidv4(), uuidv4()]
  resp = await ourClient.mutate({mutation: mutations.addAlbum, variables: {albumId: albumId1, name: 'n1'}})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addAlbum.albumId).toBe(albumId1)
  const album1 = resp.data.addAlbum
  resp = await ourClient.mutate({
    mutation: mutations.addAlbum,
    variables: {albumId: albumId2, name: 'n2', description: 'd'},
  })
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addAlbum.albumId).toBe(albumId2)
  const album2 = resp.data.addAlbum

  // check they appear correctly in User.albums
  resp = await ourClient.query({query: queries.self})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.self.albumCount).toBe(2)
  expect(resp.data.self.albums.items).toHaveLength(2)
  expect(resp.data.self.albums.items[0]).toEqual(album1)
  expect(resp.data.self.albums.items[1]).toEqual(album2)
})


test('Album art generated for 0, 1 and 4 posts in album', async () => {
  const [ourClient] = await loginCache.getCleanLogin()

  // we an album
  const albumId = uuidv4()
  let resp = await ourClient.mutate({mutation: mutations.addAlbum, variables: {albumId, name: 'n1'}})
  expect(resp.errors).toBeUndefined()
  const album = resp.data.addAlbum
  expect(album.albumId).toBe(albumId)
  expect(album.art.url).toBeTruthy()
  expect(album.art.url4k).toBeTruthy()
  expect(album.art.url1080p).toBeTruthy()
  expect(album.art.url480p).toBeTruthy()
  expect(album.art.url64p).toBeTruthy()

  // check we can access the art urls. these will throw an error if response code is not 2XX
  await rp.head({uri: album.art.url, simple: true})
  await rp.head({uri: album.art.url4k, simple: true})
  await rp.head({uri: album.art.url1080p, simple: true})
  await rp.head({uri: album.art.url480p, simple: true})
  await rp.head({uri: album.art.url64p, simple: true})

  // add a post to that album
  const postId1 = uuidv4()
  let variables = {postId: postId1, albumId, imageData}
  resp = await ourClient.mutate({mutation: mutations.addPost, variables})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addPost.postId).toBe(postId1)
  expect(resp.data.addPost.postStatus).toBe('COMPLETED')
  await misc.sleep(1000)  // let dynamo converge

  // check album has art urls and they have changed root
  resp = await ourClient.query({query: queries.album, variables: {albumId}})
  expect(resp.errors).toBeUndefined()
  const albumOnePost = resp.data.album
  expect(albumOnePost.albumId).toBe(albumId)
  expect(albumOnePost.art.url).toBeTruthy()
  expect(albumOnePost.art.url4k).toBeTruthy()
  expect(albumOnePost.art.url1080p).toBeTruthy()
  expect(albumOnePost.art.url480p).toBeTruthy()
  expect(albumOnePost.art.url64p).toBeTruthy()

  expect(albumOnePost.art.url.split('?')[0]).not.toBe(album.art.url.split('?')[0])
  expect(albumOnePost.art.url4k.split('?')[0]).not.toBe(album.art.url4k.split('?')[0])
  expect(albumOnePost.art.url1080p.split('?')[0]).not.toBe(album.art.url1080p.split('?')[0])
  expect(albumOnePost.art.url480p.split('?')[0]).not.toBe(album.art.url480p.split('?')[0])
  expect(albumOnePost.art.url64p.split('?')[0]).not.toBe(album.art.url64p.split('?')[0])

  // check we can access those urls
  await rp.head({uri: albumOnePost.art.url, simple: true})
  await rp.head({uri: albumOnePost.art.url4k, simple: true})
  await rp.head({uri: albumOnePost.art.url1080p, simple: true})
  await rp.head({uri: albumOnePost.art.url480p, simple: true})
  await rp.head({uri: albumOnePost.art.url64p, simple: true})

  // add a second post to that album
  const postId2 = uuidv4()
  variables = {postId: postId2, albumId, imageData}
  resp = await ourClient.mutate({mutation: mutations.addPost, variables})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addPost.postId).toBe(postId2)
  expect(resp.data.addPost.postStatus).toBe('COMPLETED')

  // check album has art urls that have not changed root
  resp = await ourClient.query({query: queries.album, variables: {albumId}})
  expect(resp.errors).toBeUndefined()
  const albumTwoPosts = resp.data.album
  expect(albumTwoPosts.albumId).toBe(albumId)
  expect(albumTwoPosts.art.url).toBeTruthy()
  expect(albumTwoPosts.art.url4k).toBeTruthy()
  expect(albumTwoPosts.art.url1080p).toBeTruthy()
  expect(albumTwoPosts.art.url480p).toBeTruthy()
  expect(albumTwoPosts.art.url64p).toBeTruthy()

  expect(albumTwoPosts.art.url.split('?')[0]).toBe(albumOnePost.art.url.split('?')[0])
  expect(albumTwoPosts.art.url4k.split('?')[0]).toBe(albumOnePost.art.url4k.split('?')[0])
  expect(albumTwoPosts.art.url1080p.split('?')[0]).toBe(albumOnePost.art.url1080p.split('?')[0])
  expect(albumTwoPosts.art.url480p.split('?')[0]).toBe(albumOnePost.art.url480p.split('?')[0])
  expect(albumTwoPosts.art.url64p.split('?')[0]).toBe(albumOnePost.art.url64p.split('?')[0])

  // add a third post to that album
  const postId3 = uuidv4()
  variables = {postId: postId3, albumId, imageData}
  resp = await ourClient.mutate({mutation: mutations.addPost, variables})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addPost.postId).toBe(postId3)
  expect(resp.data.addPost.postStatus).toBe('COMPLETED')

  // check album has art urls that have not changed root
  resp = await ourClient.query({query: queries.album, variables: {albumId}})
  expect(resp.errors).toBeUndefined()
  const albumThreePosts = resp.data.album
  expect(albumThreePosts.albumId).toBe(albumId)
  expect(albumThreePosts.art.url).toBeTruthy()
  expect(albumThreePosts.art.url4k).toBeTruthy()
  expect(albumThreePosts.art.url1080p).toBeTruthy()
  expect(albumThreePosts.art.url480p).toBeTruthy()
  expect(albumThreePosts.art.url64p).toBeTruthy()

  expect(albumThreePosts.art.url.split('?')[0]).toBe(albumTwoPosts.art.url.split('?')[0])
  expect(albumThreePosts.art.url4k.split('?')[0]).toBe(albumTwoPosts.art.url4k.split('?')[0])
  expect(albumThreePosts.art.url1080p.split('?')[0]).toBe(albumTwoPosts.art.url1080p.split('?')[0])
  expect(albumThreePosts.art.url480p.split('?')[0]).toBe(albumTwoPosts.art.url480p.split('?')[0])
  expect(albumThreePosts.art.url64p.split('?')[0]).toBe(albumTwoPosts.art.url64p.split('?')[0])

  // add a fourth post to that album
  const postId4 = uuidv4()
  variables = {postId: postId4, albumId, imageData}
  resp = await ourClient.mutate({mutation: mutations.addPost, variables})
  expect(resp.errors).toBeUndefined()
  expect(resp.data.addPost.postId).toBe(postId4)
  expect(resp.data.addPost.postStatus).toBe('COMPLETED')

  // check album has art urls that have changed root
  resp = await ourClient.query({query: queries.album, variables: {albumId}})
  expect(resp.errors).toBeUndefined()
  const albumFourPosts = resp.data.album
  expect(albumFourPosts.albumId).toBe(albumId)
  expect(albumFourPosts.art.url).toBeTruthy()
  expect(albumFourPosts.art.url4k).toBeTruthy()
  expect(albumFourPosts.art.url1080p).toBeTruthy()
  expect(albumFourPosts.art.url480p).toBeTruthy()
  expect(albumFourPosts.art.url64p).toBeTruthy()

  expect(albumFourPosts.art.url.split('?')[0]).not.toBe(albumThreePosts.art.url.split('?')[0])
  expect(albumFourPosts.art.url4k.split('?')[0]).not.toBe(albumThreePosts.art.url4k.split('?')[0])
  expect(albumFourPosts.art.url1080p.split('?')[0]).not.toBe(albumThreePosts.art.url1080p.split('?')[0])
  expect(albumFourPosts.art.url480p.split('?')[0]).not.toBe(albumThreePosts.art.url480p.split('?')[0])
  expect(albumFourPosts.art.url64p.split('?')[0]).not.toBe(albumThreePosts.art.url64p.split('?')[0])

  // check we can access those urls
  await rp.head({uri: albumFourPosts.art.url, simple: true})
  await rp.head({uri: albumFourPosts.art.url4k, simple: true})
  await rp.head({uri: albumFourPosts.art.url1080p, simple: true})
  await rp.head({uri: albumFourPosts.art.url480p, simple: true})
  await rp.head({uri: albumFourPosts.art.url64p, simple: true})
})
