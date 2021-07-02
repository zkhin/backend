import {v4 as uuidv4} from 'uuid'

import {cognito, eventually, generateRandomJpeg} from '../../utils'
import {mutations, queries} from '../../schema'

const imageData = new Buffer.from(generateRandomJpeg(8, 8)).toString('base64')
const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})
afterAll(async () => {
  await loginCache.reset()
})

describe('Query.postsByPaymentTicker', () => {
  let client1
  const postIdWithDefaultTicker = uuidv4()

  beforeAll(async () => {
    await loginCache.clean()
    ;({client: client1} = await loginCache.getCleanLogin())

    await client1.mutate({mutation: mutations.addPost, variables: {postId: postIdWithDefaultTicker, imageData}})
    await client1.mutate({
      mutation: mutations.addPost,
      variables: {postId: uuidv4(), imageData, paymentTicker: uuidv4()},
    })
  })

  describe('when querying for the default REAL paymentTicker', () => {
    it('returns all posts that were created without a paymentTicker', async () => {
      await eventually(async () => {
        const {data} = await client1.query({
          query: queries.postsByPaymentTicker,
          variables: {paymentTicker: 'REAL'},
        })
        expect(data).toMatchObject({posts: {items: [{postId: postIdWithDefaultTicker}], nextToken: null}})
      })
    })
  })
})
