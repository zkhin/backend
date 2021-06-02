import fs from 'fs'

import {cognito /*, eventually*/, fixturePath} from '../utils'
import {mutations /*, queries*/} from '../schema'

const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})
beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.reset())

const validSandboxReceipt = fs.readFileSync(fixturePath('appstore.receipt'), 'utf-8').trim()

test('Upload app store receipt data success', async () => {
  const {client: ourClient} = await loginCache.getCleanLogin()

  // upload a valid sandbox receipt
  await ourClient
    .mutate({
      mutation: mutations.addAppStoreReceipt,
      variables: {receiptData: validSandboxReceipt},
    })
    .then(({data}) => expect(data.addAppStoreReceipt).toBe(true))

  /**
   * Appstore auto-renewing sandbox subscriptions have their own special lifecycle:
   * https://help.apple.com/app-store-connect/#/dev7e89e149d
   *
   * Also, the sandbox appears to get reset periodically. This means that the receipt in the fixture:
   *  - represents a valid, un-expired subscription the first time it is used after a sandbox reset
   *  - it maintains that un-expired state for about an hour (see lifecycle doc for detail)
   *  - after which it becomes an expired receipt.
   * As such, the following assertion should be different depending on how often this test has been
   * run (by any developer) since the last time apple's sandbox was reset.
   */
  /*
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.self})
    expect(data.self.subscriptionLevel).toBe('BASIC')
  })
  */
})

test('Upload app store receipt data failures', async () => {
  const {client: ourClient} = await loginCache.getCleanLogin()

  await expect(
    ourClient.mutate({
      mutation: mutations.addAppStoreReceipt,
      variables: {receiptData: 'not-valid-data'},
    }),
  ).rejects.toThrow(/AppStore .* responded with status .* for receipt .*/)
})
