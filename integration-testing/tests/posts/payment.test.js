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
    await loginCache.clean()
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

  test.each([{payment: 0}, {payment: 1}])('Edit post payment property, set to %p', async ({payment}) => {
    const postId = uuidv4()

    // add the post, verify
    await client1
      .mutate({mutation: mutations.addPost, variables: {postId, imageData}})
      .then(({data: {addPost}}) => expect(addPost).toMatchObject({postId}))
    await eventually(async () => {
      const {data} = await client1.query({query: queries.post, variables: {postId}})
      expect(data.post.payment).not.toBeNull()
      expect(data.post.payment).not.toBe(payment)
    })

    // edit the post, verify
    await client1
      .mutate({mutation: mutations.editPost, variables: {postId, payment}})
      .then(({data: {editPost}}) => expect(editPost).toMatchObject({postId, payment}))
    await eventually(async () => {
      const {data} = await client1.query({query: queries.post, variables: {postId}})
      expect(data.post.payment).toBe(payment)
    })
  })
})

describe('Post.paymentTicker', () => {
  let client

  beforeAll(async () => {
    await loginCache.clean()
    ;({client} = await loginCache.getCleanLogin())
  })

  test('Cannot add ad post with paymentTicker set', async () => {
    const {errors} = await client.mutate({
      mutation: mutations.addPost,
      variables: {postId: uuidv4(), imageData, isAd: true, paymentTicker: 'foo'},
      errorPolicy: 'all',
    })
    expect(errors).toHaveLength(1)
    expect(errors[0]).toMatchObject({
      errorType: 'ClientError',
      message: expect.stringContaining('Cannot add advertisement post with paymentTicker set'),
    })
  })

  test('Cannot add post with paymentTicker set to empty string', async () => {
    const {errors} = await client.mutate({
      mutation: mutations.addPost,
      variables: {postId: uuidv4(), imageData, paymentTicker: ''},
      errorPolicy: 'all',
    })
    expect(errors).toHaveLength(1)
    expect(errors[0]).toMatchObject({
      errorType: 'ClientError',
      message: expect.stringContaining('Cannot add post with paymentTicker set to empty string'),
    })
  })

  test('Add post without setting paymentTicker', async () => {
    const postId = uuidv4()
    const paymentTickerDefault = 'REAL'
    await client.mutate({mutation: mutations.addPost, variables: {postId, imageData}})
    await eventually(async () => {
      const {data} = await client.query({query: queries.post, variables: {postId}})
      expect(data).toMatchObject({post: {postId, paymentTicker: paymentTickerDefault}})
    })
  })

  test('Add post with paymentTicker set', async () => {
    const postId = uuidv4()
    const paymentTicker = uuidv4()
    await client.mutate({mutation: mutations.addPost, variables: {postId, imageData, paymentTicker}})
    await eventually(async () => {
      const {data} = await client.query({query: queries.post, variables: {postId}})
      expect(data).toMatchObject({post: {postId, paymentTicker}})
    })
  })

  test('Edit post to set paymentTicker', async () => {
    const postId = uuidv4()
    const paymentTicker = uuidv4()

    // add post without setting paymentTicker, verify
    await client
      .mutate({mutation: mutations.addPost, variables: {postId}})
      .then(({data: {addPost}}) => expect(addPost).toMatchObject({postId}))
    await eventually(async () => {
      const {data} = await client.query({query: queries.post, variables: {postId}})
      expect(data.post.paymentTocker).not.toBe(paymentTicker)
    })

    // edit post to set paymentTicker, verify
    await client
      .mutate({mutation: mutations.editPost, variables: {postId, paymentTicker}})
      .then(({data: {editPost}}) => expect(editPost).toMatchObject({postId, paymentTicker}))
    await eventually(async () => {
      const {data} = await client.query({query: queries.post, variables: {postId}})
      expect(data.post).toMatchObject({postId, paymentTicker})
    })
  })

  test('Cannot edit post to set paymentTicker to empty string', async () => {
    const postId = uuidv4()
    const paymentTicker = uuidv4()

    // add post with paymentTicker, verify
    await client
      .mutate({mutation: mutations.addPost, variables: {postId, paymentTicker}})
      .then(({data: {addPost}}) => expect(addPost).toMatchObject({postId, paymentTicker}))

    // verify cannot edit to empty string
    await client
      .mutate({
        mutation: mutations.editPost,
        variables: {postId, paymentTicker: ''},
        errorPolicy: 'all',
      })
      .then(({errors}) => {
        expect(errors).toHaveLength(1)
        expect(errors[0]).toMatchObject({
          errorType: 'ClientError',
          message: expect.stringContaining('Cannot set paymentTicker to empty string'),
        })
      })
    await eventually(async () => {
      const {data} = await client.query({query: queries.post, variables: {postId}})
      expect(data.post).toMatchObject({postId, paymentTicker})
    })
  })
})

describe('Post.paymentTickerRequiredToView', () => {
  let client

  beforeAll(async () => {
    await loginCache.clean()
    ;({client} = await loginCache.getCleanLogin())
  })

  test('Cannot add ad post with paymentTickerRequiredToView set', async () => {
    const {errors} = await client.mutate({
      mutation: mutations.addPost,
      variables: {postId: uuidv4(), imageData, isAd: true, paymentTickerRequiredToView: false},
      errorPolicy: 'all',
    })
    expect(errors).toHaveLength(1)
    expect(errors[0]).toMatchObject({
      errorType: 'ClientError',
      message: expect.stringContaining('Cannot add advertisement post with paymentTickerRequiredToView set'),
    })
  })

  test('Add post without setting paymentTicker', async () => {
    const postId = uuidv4()
    const paymentTickerRequiredToViewDefault = false
    await client.mutate({mutation: mutations.addPost, variables: {postId, imageData}})
    await eventually(async () => {
      const {data} = await client.query({query: queries.post, variables: {postId}})
      expect(data).toMatchObject({
        post: {postId, paymentTickerRequiredToView: paymentTickerRequiredToViewDefault},
      })
    })
  })

  test('Add post with paymentTicker set', async () => {
    const postId = uuidv4()
    const paymentTickerRequiredToView = true
    await client.mutate({
      mutation: mutations.addPost,
      variables: {postId, imageData, paymentTickerRequiredToView},
    })
    await eventually(async () => {
      const {data} = await client.query({query: queries.post, variables: {postId}})
      expect(data).toMatchObject({post: {postId, paymentTickerRequiredToView}})
    })
  })

  test('Edit post to set paymentTickerRequiredToView', async () => {
    const postId = uuidv4()
    const paymentTickerRequiredToView = true

    // add post without paymentTickerRequiredToView, verify
    await client
      .mutate({mutation: mutations.addPost, variables: {postId}})
      .then(({data: {addPost}}) => expect(addPost).toMatchObject({postId}))
    await eventually(async () => {
      const {data} = await client.query({query: queries.post, variables: {postId}})
      expect(data).toMatchObject({post: {postId}})
      expect(data.post.paymentTickerRequiredToView).not.toBe(paymentTickerRequiredToView)
    })

    // set paymentTickerRequiredToView, verify
    await client
      .mutate({mutation: mutations.editPost, variables: {postId, paymentTickerRequiredToView}})
      .then(({data: {editPost}}) => expect(editPost).toMatchObject({postId, paymentTickerRequiredToView}))
    await eventually(async () => {
      const {data} = await client.query({query: queries.post, variables: {postId}})
      expect(data).toMatchObject({post: {postId, paymentTickerRequiredToView}})
    })
  })
})
