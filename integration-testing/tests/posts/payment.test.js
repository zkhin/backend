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

describe('Post.payment', () => {
  let client1, client2

  beforeAll(async () => {
    ;({client: client1} = await loginCache.getCleanLogin())
    ;({client: client2} = await loginCache.getCleanLogin())
  })

  test('Cant add post with payment set to negative number', async () => {
    const postId = uuidv4()
    await client1
      .mutate({mutation: mutations.addPost, variables: {postId, imageData, payment: -1}, errorPolicy: 'all'})
      .then(({errors}) => {
        expect(errors).toHaveLength(1)
        expect(errors[0].message).toMatch(/ClientError: Cannot add post with negative payment/)
      })
  })

  test('Cant add ad post with payment set', async () => {
    const postId = uuidv4()
    await client1
      .mutate({
        mutation: mutations.addPost,
        variables: {postId, imageData, isAd: true, payment: 1},
        errorPolicy: 'all',
      })
      .then(({errors}) => {
        expect(errors).toHaveLength(1)
        expect(errors[0].message).toMatch(/ClientError: Cannot add advertisement post with payment set/)
      })
  })

  test('Add post without setting payment, should get the default', async () => {
    const postId = uuidv4()
    await client1.mutate({mutation: mutations.addPost, variables: {postId, imageData}})
    await eventually(async () => {
      const {data} = await client1.query({query: queries.post, variables: {postId}})
      expect(data.post.postId).toBe(postId)
      expect(data.post.payment).toBeGreaterThan(0)
    })
  })

  test.each([{payment: 0}, {payment: 0.0001}])(
    'Add post with payment set to valid value: %p',
    async ({payment}) => {
      const postId = uuidv4()
      await client1.mutate({mutation: mutations.addPost, variables: {postId, imageData, payment}})
      await eventually(async () => {
        const {data} = await client1.query({query: queries.post, variables: {postId}})
        expect(data.post.postId).toBe(postId)
        expect(data.post.payment).toBe(payment)
      })
    },
  )

  test('Post.payment is visible to all user who can see the post', async () => {
    const postId = uuidv4()
    const payment = 1.1
    await client1.mutate({mutation: mutations.addPost, variables: {postId, imageData, payment}})
    await eventually(async () => {
      const {data} = await client2.query({query: queries.post, variables: {postId}})
      expect(data.post.postId).toBe(postId)
      expect(data.post.payment).toBe(payment)
    })
  })
})
