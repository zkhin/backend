const fs = require('fs')
const path = require('path')

const {cognito} = require('../../utils')
const {mutations} = require('../../schema')

const imageBytes = fs.readFileSync(path.join(__dirname, '..', '..', 'fixtures', 'dl.png'))
const imageData = new Buffer.from(imageBytes).toString('base64')
const fakeImageBytes = fs.readFileSync(path.join(__dirname, '..', '..', 'fixtures', 'grant.png'))
const fakeImageData = new Buffer.from(fakeImageBytes).toString('base64')
const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})
beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.reset())

test.skip('Document is not recognized', async () => {
  const {client} = await loginCache.getCleanLogin()

  await expect(
    client.mutate({mutation: mutations.verifyIdentity, variables: {frontsideImageData: fakeImageData}}),
  ).rejects.toThrow(/ClientError: .* `Document not recognized`/)
})

test.skip('Id verification', async () => {
  const {client, userId} = await loginCache.getCleanLogin()

  await client
    .mutate({mutation: mutations.verifyIdentity, variables: {frontsideImageData: imageData}})
    .then(({data: {verifyIdentity: user}}) => {
      expect(user.userId).toBe(userId)
    })
})
