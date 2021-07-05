import {v4 as uuidv4} from 'uuid'

import {cognito, eventually} from '../../utils'
import {mutations, queries} from '../../schema'

const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})
afterAll(async () => {
  await loginCache.reset()
})

/**
 * This test depends on the real transactions client to be disabled,
 * an thus mocking the response of get_user_tickers() to be a list of
 * two tickers: REAL and the caller's user id.
 */
describe('Queries of paginated posts, when some have paymentTicker and paymentTickerRequiredToView set', () => {
  let client1, client2
  let userId1, userId2
  const postType = 'TEXT_ONLY'
  const text = 'lore ipsum'
  const paymentTickerRequiredToView = true
  const [postId1, postId2, postId3, postId4] = [uuidv4(), uuidv4(), uuidv4(), uuidv4()]

  beforeAll(async () => {
    await loginCache.clean()
    ;({client: client1, userId: userId1} = await loginCache.getCleanLogin())
    ;({client: client2, userId: userId2} = await loginCache.getCleanLogin())

    await client1.mutate({
      mutation: mutations.addPost,
      variables: {postId: postId1, postType, text, paymentTicker: uuidv4()},
    })
    await client1.mutate({
      mutation: mutations.addPost,
      variables: {postId: postId2, postType, text, paymentTicker: uuidv4(), paymentTickerRequiredToView},
    })
    await client1.mutate({
      mutation: mutations.addPost,
      variables: {postId: postId3, postType, text, paymentTickerRequiredToView},
    })
    await client1.mutate({
      mutation: mutations.addPost,
      variables: {postId: postId4, postType, text, paymentTicker: userId2, paymentTickerRequiredToView},
    })
  })

  it('do not filter posts when the post owner looks at them', async () => {
    await eventually(async () => {
      const {data} = await client1.query({query: queries.userPosts, variables: {userId: userId1}})
      expect(data).toMatchObject({
        user: {posts: {items: [{postId: postId4}, {postId: postId3}, {postId: postId2}, {postId: postId1}]}},
      })
    })
  })

  it('filter posts when a different user looks at them', async () => {
    await eventually(async () => {
      const {data} = await client2.query({query: queries.userPosts, variables: {userId: userId1}})
      expect(data).toMatchObject({
        user: {posts: {items: [{postId: postId4}, {postId: postId3}, {postId: postId1}]}},
      })
    })
  })
})
