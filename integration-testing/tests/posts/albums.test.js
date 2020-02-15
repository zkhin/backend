/* eslint-env jest */

const fs = require('fs')
const moment = require('moment')
const path = require('path')
const uuidv4 = require('uuid/v4')

const cognito = require('../../utils/cognito.js')
const misc = require('../../utils/misc.js')
const schema = require('../../utils/schema.js')

const grantData = fs.readFileSync(path.join(__dirname, '..', '..', 'fixtures', 'grant.jpg'))
const grantDataB64 = new Buffer.from(grantData).toString('base64')
const grantContentType = 'image/jpeg'

const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})

beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.clean())


test('Create a posts in an album, album post ordering', async () => {
  const [ourClient] = await loginCache.getCleanLogin()

  // we add an album
  const albumId = uuidv4()
  let resp = await ourClient.mutate({mutation: schema.addAlbum, variables: {albumId, name: 'n'}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addAlbum']['albumId']).toBe(albumId)
  expect(resp['data']['addAlbum']['postCount']).toBe(0)
  expect(resp['data']['addAlbum']['postsLastUpdatedAt']).toBeNull()
  expect(resp['data']['addAlbum']['posts']['items']).toHaveLength(0)

  // we add an image post in that album
  const [postId1, mediaId1] = [uuidv4(), uuidv4()]
  let variables = {postId: postId1, mediaId: mediaId1, albumId, imageData: grantDataB64}
  resp = await ourClient.mutate({mutation: schema.addOneMediaPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId1)
  let postedAt = resp['data']['addPost']['postedAt']

  // check the album
  resp = await ourClient.query({query: schema.album, variables: {albumId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['album']['albumId']).toBe(albumId)
  expect(resp['data']['album']['postCount']).toBe(1)
  expect(resp['data']['album']['postsLastUpdatedAt']).toBe(postedAt)
  expect(resp['data']['album']['posts']['items']).toHaveLength(1)
  expect(resp['data']['album']['posts']['items'][0]['postId']).toBe(postId1)

  // we add another image post in that album, this one via cloudfront upload
  const [postId2, mediaId2] = [uuidv4(), uuidv4()]
  resp = await ourClient.mutate({
    mutation: schema.addOneMediaPost,
    variables: {postId: postId2, mediaId: mediaId2, albumId},
  })
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId2)
  let uploadUrl = resp['data']['addPost']['mediaObjects'][0]['uploadUrl']
  let before = moment().toISOString()
  await misc.uploadMedia(grantData, grantContentType, uploadUrl)
  await misc.sleepUntilPostCompleted(ourClient, postId2)
  let after = moment().toISOString()

  // check the album
  resp = await ourClient.query({query: schema.album, variables: {albumId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['album']['albumId']).toBe(albumId)
  expect(resp['data']['album']['postCount']).toBe(2)
  expect(before <= resp['data']['album']['postsLastUpdatedAt']).toBe(true)
  expect(after >= resp['data']['album']['postsLastUpdatedAt']).toBe(true)
  expect(resp['data']['album']['posts']['items']).toHaveLength(2)
  expect(resp['data']['album']['posts']['items'][0]['postId']).toBe(postId2)
  expect(resp['data']['album']['posts']['items'][1]['postId']).toBe(postId1)
})


test('Cant create text-only post in album, nor move one in', async () => {
  const [ourClient] = await loginCache.getCleanLogin()

  // we add an album
  const albumId = uuidv4()
  let resp = await ourClient.mutate({mutation: schema.addAlbum, variables: {albumId, name: 'n'}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addAlbum']['albumId']).toBe(albumId)

  // verify we cannot add a text-only post into that album
  const postId = uuidv4()
  let variables = {postId, text: 'lore ipsum', albumId}
  await expect(ourClient.mutate({mutation: schema.addTextOnlyPost, variables})).rejects.toBeDefined()

  // make sure that post did not end making it into the DB
  resp = await ourClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']).toBeNull()

  // we create a post, not in any album
  variables = {postId, text: 'lore ipsum'}
  resp = await ourClient.mutate({mutation: schema.addTextOnlyPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)
  expect(resp['data']['addPost']['album']).toBeNull()

  // verify we cannot move the post into their album
  variables = {postId, albumId}
  await expect(ourClient.mutate({mutation: schema.editPostAlbum, variables})).rejects.toBeDefined()

  // verify the post is unchanged
  resp = await ourClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(postId)
  expect(resp['data']['post']['album']).toBeNull()
})


test('Cant create post in or move post into album that doesnt exist', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const albumId = uuidv4()  // doesn't exist

  // verify we cannot create a post in that album
  const [postId, mediaId] = [uuidv4(), uuidv4()]
  let variables = {postId, mediaId, albumId}
  await expect(ourClient.mutate({mutation: schema.addOneMediaPost, variables})).rejects.toBeDefined()

  // make sure that post did not end making it into the DB
  let resp = await ourClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']).toBeNull()

  // we create a post, not in any album
  variables = {postId, mediaId}
  resp = await ourClient.mutate({mutation: schema.addOneMediaPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)
  expect(resp['data']['addPost']['album']).toBeNull()

  // verify neither we or them cannot move into no album
  variables = {postId, albumId}
  await expect(ourClient.mutate({mutation: schema.editPostAlbum, variables})).rejects.toBeDefined()

  // verify the post is unchanged
  resp = await ourClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(postId)
  expect(resp['data']['post']['album']).toBeNull()
})


test('Cant create post in or move post into an album thats not ours', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const [theirClient] = await loginCache.getCleanLogin()

  // they create an album
  const albumId = uuidv4()
  let resp = await theirClient.mutate({mutation: schema.addAlbum, variables: {albumId, name: 'n1'}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addAlbum']['albumId']).toBe(albumId)

  // verify we cannot create a post in their album
  const [postId, mediaId] = [uuidv4(), uuidv4()]
  let variables = {postId, mediaId, albumId}
  await expect(ourClient.mutate({mutation: schema.addOneMediaPost, variables})).rejects.toBeDefined()

  // make sure that post did not end making it into the DB
  resp = await theirClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']).toBeNull()

  // we create a post, not in any album
  variables = {postId, mediaId}
  resp = await ourClient.mutate({mutation: schema.addOneMediaPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)
  expect(resp['data']['addPost']['album']).toBeNull()
  let uploadUrl = resp['data']['addPost']['mediaObjects'][0]['uploadUrl']
  await misc.uploadMedia(grantData, grantContentType, uploadUrl)
  await misc.sleepUntilPostCompleted(ourClient, postId)

  // verify neither we or them cannot move the post into their album
  variables = {postId, albumId}
  await expect(ourClient.mutate({mutation: schema.editPostAlbum, variables})).rejects.toBeDefined()
  await expect(theirClient.mutate({mutation: schema.editPostAlbum, variables})).rejects.toBeDefined()

  // verify the post is unchanged
  resp = await theirClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(postId)
  expect(resp['data']['post']['album']).toBeNull()
})


test('Adding a post with PENDING status does not affect Album.posts until COMPLETED', async () => {
  const [ourClient] = await loginCache.getCleanLogin()

  // we add an album
  const albumId = uuidv4()
  let resp = await ourClient.mutate({mutation: schema.addAlbum, variables: {albumId, name: 'n'}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addAlbum']['albumId']).toBe(albumId)
  expect(resp['data']['addAlbum']['postCount']).toBe(0)
  expect(resp['data']['addAlbum']['postsLastUpdatedAt']).toBeNull()
  expect(resp['data']['addAlbum']['posts']['items']).toHaveLength(0)

  // we add a media post in that album (in PENDING state)
  const [postId, mediaId] = [uuidv4(), uuidv4()]
  resp = await ourClient.mutate({
    mutation: schema.addOneMediaPost,
    variables: {postId, mediaId, albumId},
  })
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)
  expect(resp['data']['addPost']['postStatus']).toBe('PENDING')
  expect(resp['data']['addPost']['album']['albumId']).toBe(albumId)
  const uploadUrl = resp['data']['addPost']['mediaObjects'][0]['uploadUrl']

  // check the album's posts, should not see the new post
  resp = await ourClient.query({query: schema.album, variables: {albumId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['album']['albumId']).toBe(albumId)
  expect(resp['data']['album']['postCount']).toBe(0)
  expect(resp['data']['album']['postsLastUpdatedAt']).toBeNull()
  expect(resp['data']['album']['posts']['items']).toHaveLength(0)

  // upload the media, thus completing the post
  await misc.uploadMedia(grantData, grantContentType, uploadUrl)
  await misc.sleepUntilPostCompleted(ourClient, postId)

  // verify the post is now COMPLETED
  resp = await ourClient.query({query: schema.post, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['post']['postId']).toBe(postId)
  expect(resp['data']['post']['postStatus']).toBe('COMPLETED')

  // check the album's posts, *should* see the new post
  resp = await ourClient.query({query: schema.album, variables: {albumId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['album']['albumId']).toBe(albumId)
  expect(resp['data']['album']['postCount']).toBe(1)
  expect(resp['data']['album']['postsLastUpdatedAt']).not.toBeNull()
  expect(resp['data']['album']['posts']['items']).toHaveLength(1)
  expect(resp['data']['album']['posts']['items'][0]['postId']).toBe(postId)
})


test('Add, remove, change albums for an existing post', async () => {
  const [ourClient] = await loginCache.getCleanLogin()

  // add two albums
  const [albumId1, albumId2] = [uuidv4(), uuidv4()]
  let resp = await ourClient.mutate({mutation: schema.addAlbum, variables: {albumId: albumId1, name: 'n1'}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addAlbum']['albumId']).toBe(albumId1)
  resp = await ourClient.mutate({mutation: schema.addAlbum, variables: {albumId: albumId2, name: 'n2'}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addAlbum']['albumId']).toBe(albumId2)

  // add a post, not in any album
  const [postId, mediaId] = [uuidv4(), uuidv4()]
  let variables = {postId, mediaId, imageData: grantDataB64}
  resp = await ourClient.mutate({mutation: schema.addOneMediaPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)
  expect(resp['data']['addPost']['postStatus']).toBe('COMPLETED')
  expect(resp['data']['addPost']['album']).toBeNull()

  // move that post into one of the albums
  let before = moment().toISOString()
  resp = await ourClient.mutate({mutation: schema.editPostAlbum, variables: {postId, albumId: albumId2}})
  let after = moment().toISOString()
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['editPostAlbum']['postId']).toBe(postId)
  expect(resp['data']['editPostAlbum']['album']['albumId']).toBe(albumId2)

  // check the album it was added to
  resp = await ourClient.query({query: schema.album, variables: {albumId: albumId2}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['album']['albumId']).toBe(albumId2)
  expect(resp['data']['album']['postCount']).toBe(1)
  expect(resp['data']['album']['posts']['items']).toHaveLength(1)
  expect(resp['data']['album']['posts']['items'][0]['postId']).toBe(postId)
  expect(before <= resp['data']['album']['postsLastUpdatedAt']).toBe(true)
  expect(after >= resp['data']['album']['postsLastUpdatedAt']).toBe(true)

  // move that post out of that album and into another
  before = moment().toISOString()
  resp = await ourClient.mutate({mutation: schema.editPostAlbum, variables: {postId, albumId: albumId1}})
  after = moment().toISOString()
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['editPostAlbum']['postId']).toBe(postId)
  expect(resp['data']['editPostAlbum']['album']['albumId']).toBe(albumId1)

  // check the album it was removed from
  resp = await ourClient.query({query: schema.album, variables: {albumId: albumId2}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['album']['albumId']).toBe(albumId2)
  expect(resp['data']['album']['postCount']).toBe(0)
  expect(resp['data']['album']['posts']['items']).toHaveLength(0)
  expect(before <= resp['data']['album']['postsLastUpdatedAt']).toBe(true)
  expect(after >= resp['data']['album']['postsLastUpdatedAt']).toBe(true)

  // check the album it was added to
  resp = await ourClient.query({query: schema.album, variables: {albumId: albumId1}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['album']['albumId']).toBe(albumId1)
  expect(resp['data']['album']['postCount']).toBe(1)
  expect(resp['data']['album']['posts']['items']).toHaveLength(1)
  expect(resp['data']['album']['posts']['items'][0]['postId']).toBe(postId)
  expect(before <= resp['data']['album']['postsLastUpdatedAt']).toBe(true)
  expect(after >= resp['data']['album']['postsLastUpdatedAt']).toBe(true)

  // remove the post from that album
  before = moment().toISOString()
  resp = await ourClient.mutate({mutation: schema.editPostAlbum, variables: {postId, albumId: null}})
  after = moment().toISOString()
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['editPostAlbum']['postId']).toBe(postId)
  expect(resp['data']['editPostAlbum']['album']).toBeNull()

  // check the album it was removed from
  resp = await ourClient.query({query: schema.album, variables: {albumId: albumId1}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['album']['albumId']).toBe(albumId1)
  expect(resp['data']['album']['postCount']).toBe(0)
  expect(resp['data']['album']['posts']['items']).toHaveLength(0)
  expect(before <= resp['data']['album']['postsLastUpdatedAt']).toBe(true)
  expect(after >= resp['data']['album']['postsLastUpdatedAt']).toBe(true)
})


test('Adding an existing post to album not in COMPLETED status has no affect on Album.post & friends', async () => {
  const [ourClient] = await loginCache.getCleanLogin()

  // add an albums
  const albumId = uuidv4()
  let resp = await ourClient.mutate({mutation: schema.addAlbum, variables: {albumId, name: 'n1'}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addAlbum']['albumId']).toBe(albumId)

  // add a media post, leave it in PENDING state
  const [postId1, mediaId] = [uuidv4(), uuidv4()]
  resp = await ourClient.mutate({
    mutation: schema.addOneMediaPost,
    variables: {postId: postId1, mediaId},
  })
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId1)
  expect(resp['data']['addPost']['postStatus']).toBe('PENDING')

  // add a media post, and archive it
  const [postId2, mediaId2] = [uuidv4(), uuidv4()]
  resp = await ourClient.mutate({
    mutation: schema.addOneMediaPost,
    variables: {postId: postId2, mediaId: mediaId2, albumId},
  })
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId2)
  resp = await ourClient.mutate({mutation: schema.archivePost, variables: {postId: postId2}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['archivePost']['postId']).toBe(postId2)
  expect(resp['data']['archivePost']['postStatus']).toBe('ARCHIVED')

  // add post the PENDING and the ARCHIVED posts to the album
  resp = await ourClient.mutate({mutation: schema.editPostAlbum, variables: {postId: postId1, albumId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['editPostAlbum']['postId']).toBe(postId1)
  expect(resp['data']['editPostAlbum']['album']['albumId']).toBe(albumId)
  resp = await ourClient.mutate({mutation: schema.editPostAlbum, variables: {postId: postId2, albumId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['editPostAlbum']['postId']).toBe(postId2)
  expect(resp['data']['editPostAlbum']['album']['albumId']).toBe(albumId)

  // check that Album.posts & friends have not changed
  resp = await ourClient.query({query: schema.album, variables: {albumId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['album']['albumId']).toBe(albumId)
  expect(resp['data']['album']['postCount']).toBe(0)
  expect(resp['data']['album']['postsLastUpdatedAt']).toBeNull()
  expect(resp['data']['album']['posts']['items']).toHaveLength(0)
})


test('Archiving a post removes it from Album.posts & friends, restoring puts it back', async () => {
  const [ourClient] = await loginCache.getCleanLogin()

  // add an album
  const albumId = uuidv4()
  let resp = await ourClient.mutate({mutation: schema.addAlbum, variables: {albumId, name: 'n1'}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addAlbum']['albumId']).toBe(albumId)

  // add a media post in the album
  const [postId, mediaId] = [uuidv4(), uuidv4()]
  let variables = {postId, mediaId, albumId, imageData: grantDataB64}
  resp = await ourClient.mutate({mutation: schema.addOneMediaPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)
  expect(resp['data']['addPost']['postStatus']).toBe('COMPLETED')
  expect(resp['data']['addPost']['album']['albumId']).toBe(albumId)

  // verify that's reflected in Album.posts and friends
  resp = await ourClient.query({query: schema.album, variables: {albumId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['album']['albumId']).toBe(albumId)
  expect(resp['data']['album']['postCount']).toBe(1)
  expect(resp['data']['album']['posts']['items']).toHaveLength(1)
  expect(resp['data']['album']['posts']['items'][0]['postId']).toBe(postId)
  let postsLastUpdatedAt = resp['data']['album']['postsLastUpdatedAt']
  expect(postsLastUpdatedAt).not.toBeNull()

  // archive the post
  resp = await ourClient.mutate({mutation: schema.archivePost, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['archivePost']['postId']).toBe(postId)
  expect(resp['data']['archivePost']['postStatus']).toBe('ARCHIVED')

  // verify that took it out of Album.post and friends
  resp = await ourClient.query({query: schema.album, variables: {albumId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['album']['albumId']).toBe(albumId)
  expect(resp['data']['album']['postCount']).toBe(0)
  expect(resp['data']['album']['posts']['items']).toHaveLength(0)
  expect(resp['data']['album']['postsLastUpdatedAt'] > postsLastUpdatedAt).toBe(true)
  postsLastUpdatedAt = resp['data']['album']['postsLastUpdatedAt']

  // restore the post
  resp = await ourClient.mutate({mutation: schema.restoreArchivedPost, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['restoreArchivedPost']['postId']).toBe(postId)
  expect(resp['data']['restoreArchivedPost']['postStatus']).toBe('COMPLETED')

  // verify its now back in Album.posts and friends
  resp = await ourClient.query({query: schema.album, variables: {albumId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['album']['albumId']).toBe(albumId)
  expect(resp['data']['album']['postCount']).toBe(1)
  expect(resp['data']['album']['posts']['items']).toHaveLength(1)
  expect(resp['data']['album']['posts']['items'][0]['postId']).toBe(postId)
  expect(resp['data']['album']['postsLastUpdatedAt'] > postsLastUpdatedAt).toBe(true)
})


test('Deleting a post removes it from Album.posts & friends', async () => {
  const [ourClient] = await loginCache.getCleanLogin()

  // add an albums
  const albumId = uuidv4()
  let resp = await ourClient.mutate({mutation: schema.addAlbum, variables: {albumId, name: 'n1'}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addAlbum']['albumId']).toBe(albumId)

  // add a media post in the album
  const [postId, mediaId] = [uuidv4(), uuidv4()]
  let variables = {postId, mediaId, albumId, imageData: grantDataB64}
  resp = await ourClient.mutate({mutation: schema.addOneMediaPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)
  expect(resp['data']['addPost']['postStatus']).toBe('COMPLETED')
  expect(resp['data']['addPost']['album']['albumId']).toBe(albumId)

  // verify that's reflected in Album.posts and friends
  resp = await ourClient.query({query: schema.album, variables: {albumId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['album']['albumId']).toBe(albumId)
  expect(resp['data']['album']['postCount']).toBe(1)
  expect(resp['data']['album']['posts']['items']).toHaveLength(1)
  expect(resp['data']['album']['posts']['items'][0]['postId']).toBe(postId)
  let postsLastUpdatedAt = resp['data']['album']['postsLastUpdatedAt']
  expect(postsLastUpdatedAt).not.toBeNull()

  // delete the post
  resp = await ourClient.mutate({mutation: schema.deletePost, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['deletePost']['postId']).toBe(postId)
  expect(resp['data']['deletePost']['postStatus']).toBe('DELETING')

  // verify that took it out of Album.post and friends
  resp = await ourClient.query({query: schema.album, variables: {albumId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['album']['albumId']).toBe(albumId)
  expect(resp['data']['album']['postCount']).toBe(0)
  expect(resp['data']['album']['posts']['items']).toHaveLength(0)
  expect(postsLastUpdatedAt < resp['data']['album']['postsLastUpdatedAt']).toBe(true)
})
