import {v4 as uuidv4} from 'uuid'

import {cognito, eventually, generateRandomJpeg} from '../../utils'
import {mutations, queries} from '../../schema'

const imageData = new Buffer.from(generateRandomJpeg(8, 8)).toString('base64')
const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})
afterAll(async () => {
  await loginCache.reset()
})

describe('Query.postsByPaymentTicker', () => {
  let client1, client2, userId2
  const postIdWithDefaultTicker = uuidv4()

  beforeAll(async () => {
    await loginCache.clean()
    ;({client: client1} = await loginCache.getCleanLogin())
    ;({client: client2, userId: userId2} = await loginCache.getCleanLogin())

    // add one post with the default paymentTicker
    await client1.mutate({mutation: mutations.addPost, variables: {postId: postIdWithDefaultTicker, imageData}})
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

  describe('when there are no posts with that paymentTicker', () => {
    it('returns no posts', async () => {
      const {data} = await client1.query({
        query: queries.postsByPaymentTicker,
        variables: {paymentTicker: uuidv4()},
      })
      expect(data).toMatchObject({posts: {items: [], nextToken: null}})
    })
  })

  describe('when there is one post with that paymentTicker', () => {
    const paymentTicker = uuidv4()
    const postId = uuidv4()

    beforeAll(async () => {
      await client1.mutate({mutation: mutations.addPost, variables: {postId, paymentTicker}})
    })

    it('returns one post', async () => {
      await eventually(async () => {
        const {data} = await client1.query({query: queries.postsByPaymentTicker, variables: {paymentTicker}})
        expect(data).toMatchObject({posts: {items: [{postId}], nextToken: null}})
      })
    })
  })

  describe('when there are three posts with that paymentTicker', () => {
    const paymentTicker = uuidv4()
    const [postId1, postId2, postId3] = [uuidv4(), uuidv4(), uuidv4()]

    beforeAll(async () => {
      await client2.mutate({mutation: mutations.addPost, variables: {postId: postId1, paymentTicker}})
      await client2.mutate({mutation: mutations.addPost, variables: {postId: postId2, paymentTicker}})
      await client1.mutate({mutation: mutations.addPost, variables: {postId: postId3, paymentTicker}})
    })

    it('returns the posts, most recently created first', async () => {
      await eventually(async () => {
        const {data} = await client1.query({query: queries.postsByPaymentTicker, variables: {paymentTicker}})
        expect(data).toMatchObject({
          posts: {items: [{postId: postId3}, {postId: postId2}, {postId: postId1}], nextToken: null},
        })
      })
    })

    describe('when using the limit parameter', () => {
      let nextToken

      it('limits the posts returned', async () => {
        const {data} = await client1.query({
          query: queries.postsByPaymentTicker,
          variables: {paymentTicker, limit: 1},
        })
        expect(data).toMatchObject({posts: {items: [{postId: postId3}], nextToken: expect.anything()}})
        nextToken = data.posts.nextToken
      })

      it('paginates the posts returned', async () => {
        const {data} = await client1.query({
          query: queries.postsByPaymentTicker,
          variables: {paymentTicker, nextToken},
        })
        expect(data).toMatchObject({posts: {items: [{postId: postId2}, {postId: postId1}], nextToken: null}})
      })
    })

    describe('when the user has been blocked by one of the post owners', () => {
      beforeAll(async () => {
        await client1.mutate({mutation: mutations.blockUser, variables: {userId: userId2}})
      })

      afterAll(async () => {
        await client1.mutate({mutation: mutations.unblockUser, variables: {userId: userId2}})
      })

      it('filters out the blockers users posts from the result', async () => {
        const {data} = await client2.query({query: queries.postsByPaymentTicker, variables: {paymentTicker}})
        expect(data).toMatchObject({posts: {items: [{postId: postId2}, {postId: postId1}], nextToken: null}})
      })
    })
  })

  describe('when there are some posts with paymentTickerRequiredToView set', () => {
    const paymentTicker = uuidv4()
    const [postId1, postId2, postId3] = [uuidv4(), uuidv4(), uuidv4()]

    beforeAll(async () => {
      await client1.mutate({
        mutation: mutations.addPost,
        variables: {postId: postId1, paymentTicker, paymentTickerRequiredToView: false},
      })
      await client1.mutate({mutation: mutations.addPost, variables: {postId: postId2, paymentTicker}})
      await client1.mutate({
        mutation: mutations.addPost,
        variables: {postId: postId3, paymentTicker, paymentTickerRequiredToView: true},
      })
    })

    describe.each([
      [null, [postId3, postId2, postId1]],
      [false, [postId3, postId2, postId1]],
      [true, [postId3]],
    ])('when setting the paymentTickerRequiredToView parameter to %p', (paymentTickerRequiredToView, postIds) => {
      it('filters out the right posts from the results', async () => {
        const {data} = await client1.query({
          query: queries.postsByPaymentTicker,
          variables: {paymentTicker, paymentTickerRequiredToView},
        })
        expect(data).toMatchObject({posts: {items: postIds.map((postId) => ({postId})), nextToken: null}})
      })
    })
  })
})
