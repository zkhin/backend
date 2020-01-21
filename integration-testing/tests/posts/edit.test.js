/* eslint-env jest */

const path = require('path')
const uuidv4 = require('uuid/v4')

const cognito = require('../../utils/cognito.js')
const misc = require('../../utils/misc.js')
const schema = require('../../utils/schema.js')

const contentType = 'image/jpeg'
const filePath = path.join(__dirname, '..', '..', 'fixtures', 'grant.jpg')

const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})

beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.clean())


test('Edit post', async () => {
  // we create an image post
  const [ourClient] = await loginCache.getCleanLogin()
  const [postId, mediaId] = [uuidv4(), uuidv4()]
  let resp = await ourClient.mutate({
    mutation: schema.addOneMediaPost,
    variables: {postId, mediaId, mediaType: 'IMAGE'},
  })
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)
  expect(resp['data']['addPost']['mediaObjects']).toHaveLength(1)
  expect(resp['data']['addPost']['mediaObjects'][0]['mediaId']).toBe(mediaId)
  const uploadUrl = resp['data']['addPost']['mediaObjects'][0]['uploadUrl']
  await misc.uploadMedia(filePath, contentType, uploadUrl)
  await misc.sleep(2000)

  // verify it has no text
  resp = await ourClient.query({query: schema.getPost, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['getPost']['text']).toBeNull()

  // change it to have some text
  const text = 'I have a voice!'
  resp = await ourClient.mutate({mutation: schema.editPost, variables: {postId, text}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['editPost']['text']).toBe(text)
  resp = await ourClient.query({query: schema.getPost, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['getPost']['text']).toBe(text)

  // go back to no text
  resp = await ourClient.mutate({mutation: schema.editPost, variables: {postId, text: ''}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['editPost']['text']).toBeNull()
  resp = await ourClient.query({query: schema.getPost, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['getPost']['text']).toBeNull()
})


test('Edit post failures for for various scenarios', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const postId = uuidv4()

  // verify we can't edit a post that doesn't exist
  await expect(ourClient.mutate({
    mutation: schema.editPost,
    variables: {postId, text: 'keep calm'},
  })).rejects.toThrow('does not exist')

  // we add a text-only post
  let resp = await ourClient.mutate({mutation: schema.addTextOnlyPost, variables: {postId, text: 'my wayward son'}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postStatus']).toBe('COMPLETED')

  // verify we can't give it a content-less edit
  await expect(ourClient.mutate({
    mutation: schema.editPost,
    variables: {postId}
  })).rejects.toThrow('Empty edit requested')

  // verify another user can't edit it
  const [theirClient] = await loginCache.getCleanLogin()
  await expect(theirClient.mutate({
    mutation: schema.editPost,
    variables: {postId, text: 'go'},
  })).rejects.toThrow("another User's post")

  // verify we can't edit it into a content-less post
  await expect(ourClient.mutate({
    mutation: schema.editPost,
    variables: {postId, text: ''},
  })).rejects.toThrow('post')

  // verify we can edit it!
  const text = 'stop'
  resp = await ourClient.mutate({mutation: schema.editPost, variables: {postId, text}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['editPost']['text']).toBe(text)
})


test('Edit post edits the copies of posts in followers feeds', async () => {
  const [ourClient, ourUserId] = await loginCache.getCleanLogin()

  // a user that follows us
  const [theirClient] = await loginCache.getCleanLogin()
  let resp = await theirClient.mutate({mutation: schema.followUser, variables: {userId: ourUserId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['followUser']['followedStatus']).toBe('FOLLOWING')

  // we add a text-only post
  const postId = uuidv4()
  const postText = 'je suis le possion?'
  resp = await ourClient.mutate({mutation: schema.addTextOnlyPost, variables: {postId, text: postText}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postStatus']).toBe('COMPLETED')

  // check that post text in their feed
  resp = await theirClient.query({query: schema.getFeed})
  expect(resp['data']['getFeed']['items']).toHaveLength(1)
  expect(resp['data']['getFeed']['items'][0]['postId']).toBe(postId)
  expect(resp['data']['getFeed']['items'][0]['text']).toBe(postText)

  // edit the post
  const newText = 'no, vous est le fromage!'
  resp = await ourClient.mutate({mutation: schema.editPost, variables: {postId, text: newText}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['editPost']['text']).toBe(newText)

  // check that post text in their feed was edited
  resp = await theirClient.query({query: schema.getFeed})
  expect(resp['data']['getFeed']['items']).toHaveLength(1)
  expect(resp['data']['getFeed']['items'][0]['postId']).toBe(postId)
  expect(resp['data']['getFeed']['items'][0]['text']).toBe(newText)
})


test('Edit post set commentsDisabled', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const postId = uuidv4()

  // we add a post
  let resp = await ourClient.mutate({mutation: schema.addTextOnlyPost, variables: {postId, text: 'my wayward son'}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postStatus']).toBe('COMPLETED')
  expect(resp['data']['addPost']['commentsDisabled']).toBe(false)

  // edit the coment disabled status
  resp = await ourClient.mutate({mutation: schema.editPost, variables: {postId, commentsDisabled: true}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['editPost']['commentsDisabled']).toBe(true)

  // check it saved to db
  resp = await ourClient.query({query: schema.getPost, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['getPost']['commentsDisabled']).toBe(true)

  // edit the coment disabled status
  resp = await ourClient.mutate({mutation: schema.editPost, variables: {postId, commentsDisabled: false}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['editPost']['commentsDisabled']).toBe(false)
})


test('Edit post set likesDisabled', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const postId = uuidv4()

  // we add a post
  let resp = await ourClient.mutate({mutation: schema.addTextOnlyPost, variables: {postId, text: 'my wayward son'}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postStatus']).toBe('COMPLETED')
  expect(resp['data']['addPost']['likesDisabled']).toBe(false)

  // edit the likes disabled status
  resp = await ourClient.mutate({mutation: schema.editPost, variables: {postId, likesDisabled: true}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['editPost']['likesDisabled']).toBe(true)

  // check it saved to db
  resp = await ourClient.query({query: schema.getPost, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['getPost']['likesDisabled']).toBe(true)

  // edit the likes disabled status
  resp = await ourClient.mutate({mutation: schema.editPost, variables: {postId, likesDisabled: false}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['editPost']['likesDisabled']).toBe(false)
})


test('Edit post set verificationHidden', async () => {
  const [ourClient] = await loginCache.getCleanLogin()
  const postId = uuidv4()

  // we add a post
  let resp = await ourClient.mutate({mutation: schema.addTextOnlyPost, variables: {postId, text: 'my wayward son'}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postStatus']).toBe('COMPLETED')
  expect(resp['data']['addPost']['verificationHidden']).toBe(false)

  // edit the verification disabled status
  resp = await ourClient.mutate({mutation: schema.editPost, variables: {postId, verificationHidden: true}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['editPost']['verificationHidden']).toBe(true)

  // check it saved to db
  resp = await ourClient.query({query: schema.getPost, variables: {postId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['getPost']['verificationHidden']).toBe(true)

  // edit the verification disabled status
  resp = await ourClient.mutate({mutation: schema.editPost, variables: {postId, verificationHidden: false}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['editPost']['verificationHidden']).toBe(false)
})
