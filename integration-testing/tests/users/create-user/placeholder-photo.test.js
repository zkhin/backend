/* eslint-env jest */

const fs = require('fs')
const path = require('path')
const uuidv4 = require('uuid/v4')

const cognito = require('../../../utils/cognito.js')
const schema = require('../../../utils/schema.js')

const grantData = fs.readFileSync(path.join(__dirname, '..', '..', '..', 'fixtures', 'grant.jpg'))
const grantDataB64 = new Buffer.from(grantData).toString('base64')

const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})

beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.clean())


// expects the placeholder photos directory in the REAL-Themes bucket *not* to be set up
test('Mutation.createCognitoOnlyUser with no placeholder photos in bucket fails softly', async () => {
  const [client, userId, , , username] = await loginCache.getCleanLogin()

  // reset the user to clear & re-initialize their presence from dynamo
  let resp = await client.mutate({mutation: schema.resetUser, variables: {newUsername: username}})
  expect(resp['errors']).toBeUndefined()

  resp = await client.query({query: schema.self})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['userId']).toBe(userId)
  expect(resp['data']['self']['photoUrl']).toBeNull()
  expect(resp['data']['self']['photoUrl64p']).toBeNull()
  expect(resp['data']['self']['photoUrl480p']).toBeNull()
  expect(resp['data']['self']['photoUrl1080p']).toBeNull()
  expect(resp['data']['self']['photoUrl4k']).toBeNull()
})


/* This test expects the placeholder photos directory in the REAL-Themes bucket
 * to be set up with exactly one placeholder photo */
test.skip('Mutation.createCognitoOnlyUser with placeholder photo in bucket works', async () => {
  // These variables must be filed in correctly
  const placeholderPhotosDomain = ''
  const placeholderPhotosDirectory = ''
  const placeholderPhotoCode = ''

  const [client, userId, , , username] = await loginCache.getCleanLogin()

  // reset the user to clear & re-initialize their presence from dynamo
  let resp = await client.mutate({mutation: schema.resetUser, variables: {newUsername: username}})
  expect(resp['errors']).toBeUndefined()

  resp = await client.query({query: schema.self})
  expect(resp['errors']).toBeUndefined()
  const urlRoot = `https://${placeholderPhotosDomain}/${placeholderPhotosDirectory}/${placeholderPhotoCode}/`
  const urlRootRE = new RegExp(`^${urlRoot}.*$`)
  expect(resp['data']['self']['userId']).toBe(userId)

  expect(resp['data']['self']['photoUrl']).toMatch(urlRootRE)
  expect(resp['data']['self']['photoUrl64p']).toMatch(urlRootRE)
  expect(resp['data']['self']['photoUrl480p']).toMatch(urlRootRE)
  expect(resp['data']['self']['photoUrl1080p']).toMatch(urlRootRE)
  expect(resp['data']['self']['photoUrl4k']).toMatch(urlRootRE)

  expect(resp['data']['self']['photoUrl']).toMatch(/.*\/native\.jpg$/)
  expect(resp['data']['self']['photoUrl64p']).toMatch(/.*\/64p\.jpg$/)
  expect(resp['data']['self']['photoUrl480p']).toMatch(/.*\/480p\.jpg$/)
  expect(resp['data']['self']['photoUrl1080p']).toMatch(/.*\/1080p\.jpg$/)
  expect(resp['data']['self']['photoUrl4k']).toMatch(/.*\/4K\.jpg$/)

  // If you want to manually verify these urls, here they are
  //console.log(resp['data']['self']['photoUrl'])
  //console.log(resp['data']['self']['photoUrl64p'])
  //console.log(resp['data']['self']['photoUrl480p'])
  //console.log(resp['data']['self']['photoUrl1080p'])
  //console.log(resp['data']['self']['photoUrl4k'])

  // now set a custom profile photo, and make sure the placeholder urls go away

  // create a post with an image
  const [postId, mediaId] = [uuidv4(), uuidv4()]
  let variables = {postId, mediaId, imageData: grantDataB64}
  resp = await client.mutate({mutation: schema.addOneMediaPost, variables})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['addPost']['postId']).toBe(postId)
  expect(resp['data']['addPost']['postStatus']).toBe('COMPLETED')
  expect(resp['data']['addPost']['mediaObjects']).toHaveLength(1)
  expect(resp['data']['addPost']['mediaObjects'][0]['mediaId']).toBe(mediaId)
  expect(resp['data']['addPost']['mediaObjects'][0]['mediaStatus']).toBe('UPLOADED')

  // get our uploaded/completed media, we should have just that one media object
  resp = await client.query({query: schema.userMediaObjects})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['user']['mediaObjects']['items']).toHaveLength(1)
  expect(resp['data']['user']['mediaObjects']['items'][0]['mediaId']).toBe(mediaId)

  // set our photo
  resp = await client.mutate({mutation: schema.setUserDetails, variables: {photoMediaId: mediaId}})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['setUserDetails']['photoUrl']).toBeTruthy()
  expect(resp['data']['setUserDetails']['photoUrl64p']).toBeTruthy()
  expect(resp['data']['setUserDetails']['photoUrl480p']).toBeTruthy()
  expect(resp['data']['setUserDetails']['photoUrl1080p']).toBeTruthy()
  expect(resp['data']['setUserDetails']['photoUrl4k']).toBeTruthy()

  // check that it is really set already set
  resp = await client.query({query: schema.self})
  expect(resp['errors']).toBeUndefined()
  expect(resp['data']['self']['photoUrl']).toBeTruthy()
  expect(resp['data']['self']['photoUrl64p']).toBeTruthy()
  expect(resp['data']['self']['photoUrl480p']).toBeTruthy()
  expect(resp['data']['self']['photoUrl1080p']).toBeTruthy()
  expect(resp['data']['self']['photoUrl4k']).toBeTruthy()

  // check that the urls are no longer coming from the placeholder photos bucket
  expect(resp['data']['self']['photoUrl']).not.toMatch(urlRootRE)
  expect(resp['data']['self']['photoUrl64p']).not.toMatch(urlRootRE)
  expect(resp['data']['self']['photoUrl480p']).not.toMatch(urlRootRE)
  expect(resp['data']['self']['photoUrl1080p']).not.toMatch(urlRootRE)
  expect(resp['data']['self']['photoUrl4k']).not.toMatch(urlRootRE)
})
