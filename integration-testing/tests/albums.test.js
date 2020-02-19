/* eslint-env jest */

const moment = require('moment')
const rp = require('request-promise-native')
const uuidv4 = require('uuid/v4')

const cognito = require('../utils/cognito.js')
const misc = require('../utils/misc.js')
const schema = require('../utils/schema.js')

const imageData = misc.generateRandomJpeg(8, 8)
const imageDataB64 = new Buffer.from(imageData).toString('base64')

const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})

beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.clean())


test('Add, read, and delete an album', async () => {
  const [ourClient] = await loginCache.getCleanLogin()

  // we add an album with minimal options
  const albumId = uuidv4()
  const name = 'album name'
  const before = moment().toISOString()
  let resp = await ourClient.mutate({mutation: schema.addAlbum, variables: {albumId, name}})
  const after = moment().toISOString()
  expect(resp['errors']).toBeUndefined()
  const album = resp['data']['addAlbum']
  expect(album['albumId']).toBe(albumId)
  expect(album['name']).toBe(name)
  expect(album['description']).toBeNull()
  expect(album['url']).not.toBeNull()
  expect(album['url4k']).not.toBeNull()
  expect(album['url1080p']).not.toBeNull()
  expect(album['url480p']).not.toBeNull()
  expect(album['url64p']).not.toBeNull()
  expect(album['postCount']).toBe(0)
  expect(album['postsLastUpdatedAt']).toBeNull()
  expect(album['posts']['items']).toHaveLength(0)
  expect(before <= album['createdAt']).toBe(true)
  expect(after >= album['createdAt']).toBe(true)

  // read that album via direct access
  resp = await ourClient.query({query: schema.album, variables: {albumId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['album']).toEqual(album)

  // delete the album
  resp = await ourClient.mutate({mutation: schema.deleteAlbum, variables: {albumId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['deleteAlbum']).toEqual(album)

  // check its really gone
  resp = await ourClient.query({query: schema.album, variables: {albumId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['album']).toBeNull()
})


test('Edit an album', async () => {
  const [ourClient] = await loginCache.getCleanLogin()

  // we add an album with maximal options
  const albumId = uuidv4()
  const orgName = 'org album name'
  const orgDescription = 'org album desc'
  let resp = await ourClient.mutate({
    mutation: schema.addAlbum,
    variables: {albumId, name: orgName, description: orgDescription},
  })
  expect(resp['errors']).toBeUndefined()
  const orgAlbum = resp['data']['addAlbum']
  expect(orgAlbum['albumId']).toBe(albumId)
  expect(orgAlbum['name']).toBe(orgName)
  expect(orgAlbum['description']).toBe(orgDescription)

  // edit the options on that album
  const newName = 'new album name'
  const newDescription = 'new album desc'
  resp = await ourClient.mutate({
    mutation: schema.editAlbum,
    variables: {albumId, name: newName, description: newDescription},
  })
  expect(resp['errors']).toBeUndefined()
  const editedAlbum = resp['data']['editAlbum']
  expect(editedAlbum['albumId']).toBe(albumId)
  expect(editedAlbum['name']).toBe(newName)
  expect(editedAlbum['description']).toBe(newDescription)
  expect({
    ...editedAlbum,
    ...{name: orgAlbum['name'], description: orgAlbum['description']}
  }).toEqual(orgAlbum)

  // verify those stuck in the DB
  resp = await ourClient.query({query: schema.album, variables: {albumId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['album']).toEqual(editedAlbum)

  // delete the options which we can on that album
  resp = await ourClient.mutate({mutation: schema.editAlbum, variables: {albumId, description: ''}})
  expect(resp['errors']).toBeUndefined()
  const clearedAlbum = resp['data']['editAlbum']
  expect(clearedAlbum['albumId']).toBe(albumId)
  expect(clearedAlbum['name']).toBe(newName)
  expect(clearedAlbum['description']).toBeNull()
  expect({
    ...clearedAlbum,
    ...{description: editedAlbum['description']}
  }).toEqual(editedAlbum)

  // verify those stuck in the DB
  resp = await ourClient.query({query: schema.album, variables: {albumId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['album']).toEqual(clearedAlbum)

  // verify we can't null out the album name
  await expect(ourClient.mutate({mutation: schema.editAlbum, variables: {albumId, name: ''}})).rejects.toBeDefined()
})


test('Cant create two albums with same id', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()

  // we add an album
  const albumId = uuidv4()
  let resp = await ourClient.mutate({mutation: schema.addAlbum, variables: {albumId, name: 'n'}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addAlbum']['albumId']).toBe(albumId)

  // verify neither us nor them can add another album with same id
  await expect(ourClient.mutate({mutation: schema.addAlbum, variables: {albumId, name: 'r'}})).rejects.toBeDefined()
  await expect(theirClient.mutate({mutation: schema.addAlbum, variables: {albumId, name: 'r'}})).rejects.toBeDefined()
})

test('Cant edit or delete somebody elses album', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()

  // we add an album
  const albumId = uuidv4()
  let resp = await ourClient.mutate({mutation: schema.addAlbum, variables: {albumId, name: 'n'}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addAlbum']['albumId']).toBe(albumId)

  // verify they can't edit it nor delete it
  const name = 'name'
  await expect(theirClient.mutate({mutation: schema.editAlbum, variables: {albumId, name}})).rejects.toBeDefined()
  await expect(theirClient.mutate({mutation: schema.deleteAlbum, variables: {albumId}})).rejects.toBeDefined()

  // verify it's still there
  resp = await theirClient.query({query: schema.album, variables: {albumId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['album']['albumId']).toBe(albumId)
})


test('Empty album edit raises error', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()

  // we add an album
  const albumId = uuidv4()
  let resp = await ourClient.mutate({mutation: schema.addAlbum, variables: {albumId, name: 'n'}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addAlbum']['albumId']).toBe(albumId)

  // verify calling edit without specifying anything to edit is an error
  await expect(theirClient.mutate({mutation: schema.editAlbum, variables: {albumId}})).rejects.toBeDefined()
})


test('Cant edit, delete an album that doesnt exist', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const albumId = uuidv4()  // doesnt exist

  // cant edit or delete the non-existing album
  await expect(ourClient.mutate({mutation: schema.editAlbum, variables: {albumId, name: 'n'}})).rejects.toBeDefined()
  await expect(ourClient.mutate({mutation: schema.deleteAlbum, variables: {albumId}})).rejects.toBeDefined()
})


test('User.albums and Query.album block privacy', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient, theirUserId] = await loginCache.getCleanLogin()

  // we add an album
  const albumId = uuidv4()
  let resp = await ourClient.mutate({mutation: schema.addAlbum, variables: {albumId, name: 'n'}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addAlbum']['albumId']).toBe(albumId)

  // check they can see our albums
  resp = await theirClient.query({query: schema.user, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['albumCount']).toBe(1)
  expect(resp['data']['user']['albums']['items']).toHaveLength(1)

  // check they can see the album directly
  resp = await theirClient.query({query: schema.album, variables: {albumId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['album']['albumId']).toBe(albumId)

  // we block them
  resp = await ourClient.mutate({mutation: schema.blockUser, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['blockUser']['userId']).toBe(theirUserId)

  // check they cannot see our albums
  resp = await theirClient.query({query: schema.user, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['albumCount']).toBeNull()
  expect(resp['data']['user']['albums']).toBeNull()

  // check they cannot see the album directly
  resp = await theirClient.query({query: schema.album, variables: {albumId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['album']).toBeNull()

  // we unblock them
  resp = await ourClient.mutate({mutation: schema.unblockUser, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['unblockUser']['userId']).toBe(theirUserId)

  // check they can see our albums
  resp = await theirClient.query({query: schema.user, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['albumCount']).toBe(1)
  expect(resp['data']['user']['albums']['items']).toHaveLength(1)

  // check they can see the album directly
  resp = await theirClient.query({query: schema.album, variables: {albumId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['album']['albumId']).toBe(albumId)
})


test('User.albums and Query.album private user privacy', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()
  const [theirClient, theirUserId] = await loginCache.getCleanLogin()

  // check they *can* see our albums
  let resp = await theirClient.query({query: schema.user, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['albumCount']).toBe(0)
  expect(resp['data']['user']['albums']['items']).toHaveLength(0)

  // we go private
  resp = await ourClient.mutate({mutation: schema.setUserPrivacyStatus, variables: {privacyStatus: 'PRIVATE'}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['setUserDetails']['privacyStatus']).toBe('PRIVATE')

  // we add an album
  const albumId = uuidv4()
  resp = await ourClient.mutate({mutation: schema.addAlbum, variables: {albumId, name: 'n'}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addAlbum']['albumId']).toBe(albumId)

  // check they cannot see our albums
  resp = await theirClient.query({query: schema.user, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['albumCount']).toBeNull()
  expect(resp['data']['user']['albums']).toBeNull()

  // check they cannot see the album directly
  resp = await theirClient.query({query: schema.album, variables: {albumId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['album']).toBeNull()

  // they request to follow us
  resp = await theirClient.mutate({mutation: schema.followUser, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['followUser']['followedStatus']).toBe('REQUESTED')

  // check they cannot see our albums
  resp = await theirClient.query({query: schema.user, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['albumCount']).toBeNull()
  expect(resp['data']['user']['albums']).toBeNull()

  // check they cannot see the album directly
  resp = await theirClient.query({query: schema.album, variables: {albumId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['album']).toBeNull()

  // we accept their follow request
  resp = await ourClient.mutate({mutation: schema.acceptFollowerUser, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['acceptFollowerUser']['followerStatus']).toBe('FOLLOWING')

  // check they *can* see our albums
  resp = await theirClient.query({query: schema.user, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['albumCount']).toBe(1)
  expect(resp['data']['user']['albums']['items']).toHaveLength(1)

  // check they *can* see the album directly
  resp = await theirClient.query({query: schema.album, variables: {albumId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['album']['albumId']).toBe(albumId)

  // now we deny their follow request
  resp = await ourClient.mutate({mutation: schema.denyFollowerUser, variables: {userId: theirUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['denyFollowerUser']['followerStatus']).toBe('DENIED')

  // check they cannot see our albums
  resp = await theirClient.query({query: schema.user, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['albumCount']).toBeNull()
  expect(resp['data']['user']['albums']).toBeNull()

  // check they cannot see the album directly
  resp = await theirClient.query({query: schema.album, variables: {albumId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['album']).toBeNull()
})


test('User.albums matches direct access, ordering', async () => {
  const [ourClient] = await loginCache.getCleanLogin()

  // check we have no albums
  let resp = await ourClient.query({query: schema.self})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['albumCount']).toBe(0)
  expect(resp['data']['self']['albums']['items']).toHaveLength(0)

  // we add two albums - one minimal one maximal
  const [albumId1, albumId2] = [uuidv4(), uuidv4()]
  resp = await ourClient.mutate({mutation: schema.addAlbum, variables: {albumId: albumId1, name: 'n1'}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addAlbum']['albumId']).toBe(albumId1)
  const album1 = resp['data']['addAlbum']
  resp = await ourClient.mutate({
    mutation: schema.addAlbum,
    variables: {albumId: albumId2, name: 'n2', description: 'd'},
  })
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addAlbum']['albumId']).toBe(albumId2)
  const album2 = resp['data']['addAlbum']

  // check they appear correctly in User.albums
  resp = await ourClient.query({query: schema.self})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['albumCount']).toBe(2)
  expect(resp['data']['self']['albums']['items']).toHaveLength(2)
  expect(resp['data']['self']['albums']['items'][0]).toEqual(album1)
  expect(resp['data']['self']['albums']['items'][1]).toEqual(album2)
})


test('Album art generated for 0, 1 and 4 posts in album', async () => {
  const [ourClient] = await loginCache.getCleanLogin()

  // we an album
  const albumId = uuidv4()
  let resp = await ourClient.mutate({mutation: schema.addAlbum, variables: {albumId, name: 'n1'}})
  expect(resp['errors']).toBeUndefined()
  const album = resp['data']['addAlbum']
  expect(album['albumId']).toBe(albumId)
  expect(album['url']).not.toBeNull()
  expect(album['url4k']).not.toBeNull()
  expect(album['url1080p']).not.toBeNull()
  expect(album['url480p']).not.toBeNull()
  expect(album['url64p']).not.toBeNull()

  // check we can access the art urls. these will throw an error if response code is not 2XX
  await rp.head({uri: album['url'], simple: true})
  await rp.head({uri: album['url4k'], simple: true})
  await rp.head({uri: album['url1080p'], simple: true})
  await rp.head({uri: album['url480p'], simple: true})
  await rp.head({uri: album['url64p'], simple: true})

  // add a post to that album
  const [postId1, mediaId1] = [uuidv4(), uuidv4()]
  let variables = {postId: postId1, mediaId: mediaId1, albumId, imageData: imageDataB64}
  resp = await ourClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId1)
  expect(resp['data']['addPost']['postStatus']).toBe('COMPLETED')

  // check album has art urls and they have changed root
  resp = await ourClient.query({query: schema.album, variables: {albumId}})
  expect(resp['errors']).toBeUndefined()
  const albumOnePost = resp['data']['album']
  expect(albumOnePost['albumId']).toBe(albumId)
  expect(albumOnePost['url']).not.toBeNull()
  expect(albumOnePost['url4k']).not.toBeNull()
  expect(albumOnePost['url1080p']).not.toBeNull()
  expect(albumOnePost['url480p']).not.toBeNull()
  expect(albumOnePost['url64p']).not.toBeNull()
  expect(albumOnePost['url'].split('?')[0]).not.toBe(album['url'].split('?')[0])
  expect(albumOnePost['url4k'].split('?')[0]).not.toBe(album['url4k'].split('?')[0])
  expect(albumOnePost['url1080p'].split('?')[0]).not.toBe(album['url1080p'].split('?')[0])
  expect(albumOnePost['url480p'].split('?')[0]).not.toBe(album['url480p'].split('?')[0])
  expect(albumOnePost['url64p'].split('?')[0]).not.toBe(album['url64p'].split('?')[0])

  // check we can access those urls
  await rp.head({uri: albumOnePost['url'], simple: true})
  await rp.head({uri: albumOnePost['url4k'], simple: true})
  await rp.head({uri: albumOnePost['url1080p'], simple: true})
  await rp.head({uri: albumOnePost['url480p'], simple: true})
  await rp.head({uri: albumOnePost['url64p'], simple: true})

  // add a second post to that album
  const [postId2, mediaId2] = [uuidv4(), uuidv4()]
  variables = {postId: postId2, mediaId: mediaId2, albumId, imageData: imageDataB64}
  resp = await ourClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId2)
  expect(resp['data']['addPost']['postStatus']).toBe('COMPLETED')

  // check album has art urls that have not changed root
  resp = await ourClient.query({query: schema.album, variables: {albumId}})
  expect(resp['errors']).toBeUndefined()
  const albumTwoPosts = resp['data']['album']
  expect(albumTwoPosts['albumId']).toBe(albumId)
  expect(albumTwoPosts['url']).not.toBeNull()
  expect(albumTwoPosts['url4k']).not.toBeNull()
  expect(albumTwoPosts['url1080p']).not.toBeNull()
  expect(albumTwoPosts['url480p']).not.toBeNull()
  expect(albumTwoPosts['url64p']).not.toBeNull()
  expect(albumTwoPosts['url'].split('?')[0]).toBe(albumOnePost['url'].split('?')[0])
  expect(albumTwoPosts['url4k'].split('?')[0]).toBe(albumOnePost['url4k'].split('?')[0])
  expect(albumTwoPosts['url1080p'].split('?')[0]).toBe(albumOnePost['url1080p'].split('?')[0])
  expect(albumTwoPosts['url480p'].split('?')[0]).toBe(albumOnePost['url480p'].split('?')[0])
  expect(albumTwoPosts['url64p'].split('?')[0]).toBe(albumOnePost['url64p'].split('?')[0])

  // add a third post to that album
  const [postId3, mediaId3] = [uuidv4(), uuidv4()]
  variables = {postId: postId3, mediaId: mediaId3, albumId, imageData: imageDataB64}
  resp = await ourClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId3)
  expect(resp['data']['addPost']['postStatus']).toBe('COMPLETED')

  // check album has art urls that have not changed root
  resp = await ourClient.query({query: schema.album, variables: {albumId}})
  expect(resp['errors']).toBeUndefined()
  const albumThreePosts = resp['data']['album']
  expect(albumThreePosts['albumId']).toBe(albumId)
  expect(albumThreePosts['url']).not.toBeNull()
  expect(albumThreePosts['url4k']).not.toBeNull()
  expect(albumThreePosts['url1080p']).not.toBeNull()
  expect(albumThreePosts['url480p']).not.toBeNull()
  expect(albumThreePosts['url64p']).not.toBeNull()
  expect(albumThreePosts['url'].split('?')[0]).toBe(albumTwoPosts['url'].split('?')[0])
  expect(albumThreePosts['url4k'].split('?')[0]).toBe(albumTwoPosts['url4k'].split('?')[0])
  expect(albumThreePosts['url1080p'].split('?')[0]).toBe(albumTwoPosts['url1080p'].split('?')[0])
  expect(albumThreePosts['url480p'].split('?')[0]).toBe(albumTwoPosts['url480p'].split('?')[0])
  expect(albumThreePosts['url64p'].split('?')[0]).toBe(albumTwoPosts['url64p'].split('?')[0])

  // add a fourth post to that album
  const [postId4, mediaId4] = [uuidv4(), uuidv4()]
  variables = {postId: postId4, mediaId: mediaId4, albumId, imageData: imageDataB64}
  resp = await ourClient.mutate({mutation: schema.addPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId4)
  expect(resp['data']['addPost']['postStatus']).toBe('COMPLETED')

  // check album has art urls that have changed root
  resp = await ourClient.query({query: schema.album, variables: {albumId}})
  expect(resp['errors']).toBeUndefined()
  const albumFourPosts = resp['data']['album']
  expect(albumFourPosts['albumId']).toBe(albumId)
  expect(albumFourPosts['url']).not.toBeNull()
  expect(albumFourPosts['url4k']).not.toBeNull()
  expect(albumFourPosts['url1080p']).not.toBeNull()
  expect(albumFourPosts['url480p']).not.toBeNull()
  expect(albumFourPosts['url64p']).not.toBeNull()
  expect(albumFourPosts['url'].split('?')[0]).not.toBe(albumThreePosts['url'].split('?')[0])
  expect(albumFourPosts['url4k'].split('?')[0]).not.toBe(albumThreePosts['url4k'].split('?')[0])
  expect(albumFourPosts['url1080p'].split('?')[0]).not.toBe(albumThreePosts['url1080p'].split('?')[0])
  expect(albumFourPosts['url480p'].split('?')[0]).not.toBe(albumThreePosts['url480p'].split('?')[0])
  expect(albumFourPosts['url64p'].split('?')[0]).not.toBe(albumThreePosts['url64p'].split('?')[0])

  // check we can access those urls
  await rp.head({uri: albumFourPosts['url'], simple: true})
  await rp.head({uri: albumFourPosts['url4k'], simple: true})
  await rp.head({uri: albumFourPosts['url1080p'], simple: true})
  await rp.head({uri: albumFourPosts['url480p'], simple: true})
  await rp.head({uri: albumFourPosts['url64p'], simple: true})
})
