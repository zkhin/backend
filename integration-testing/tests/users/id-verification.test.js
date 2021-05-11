const fs = require('fs')
const path = require('path')

const cognito = require('../../utils/cognito')
const {mutations} = require('../../schema')

const imageBytes = fs.readFileSync(path.join(__dirname, '..', '..', 'fixtures', 'grant.jpg'))
const imageData = new Buffer.from(imageBytes).toString('base64')
const loginCache = new cognito.AppSyncLoginCache()
jest.retryTimes(1)

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})
beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.reset())

test('Id verification', async () => {
  const {client, userId} = await loginCache.getCleanLogin()

  await client
    .mutate({
      mutation: mutations.verifyId,
      variables: {
        frontsideImageData: imageData,
        country: 'USA',
        idType: 'ID_CARD',
        imageType: 'JPEG',
      },
    })
    .then(({data: {verifyId: user}}) => {
      expect(user.userId).toBe(userId)
    })
})
