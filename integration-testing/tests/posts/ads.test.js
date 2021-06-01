const {v4: uuidv4} = require('uuid')

const {cognito, eventually, generateRandomJpeg, sleep} = require('../../utils')
const {mutations, queries} = require('../../schema')

const imageBytes = generateRandomJpeg(8, 8)
const imageData = new Buffer.from(imageBytes).toString('base64')
const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})
afterAll(async () => await loginCache.reset())

describe('Adding ad posts', () => {
  let client

  beforeAll(async () => {
    await loginCache.clean()
    ;({client} = await loginCache.getCleanLogin())
  })

  test('Can add a non-ad post', async () => {
    const postId = uuidv4()
    await client
      .mutate({mutation: mutations.addPost, variables: {postId, imageData}})
      .then(({data}) => expect(data.addPost.postId).toBe(postId))
    await eventually(async () => {
      const {data} = await client.query({query: queries.post, variables: {postId}})
      expect(data.post.postId).toBe(postId)
      expect(data.post.postStatus).toBe('COMPLETED')
      expect(data.post.adStatus).toBe('NOT_AD')
      expect(data.post.adPayment).toBeNull()
    })
  })

  test.each([
    [{isAd: true}, 'Cannot add advertisement post without setting adPayment'],
    [{adPayment: 0.0}, 'Cannot add non-advertisement post with adPayment set'],
    [{adPaymentPeriod: 'P1D'}, 'Cannot add non-advertisement post with adPaymentPeriod set'],
    [{isAd: false, adPayment: 1.1}, 'Cannot add non-advertisement post with adPayment set'],
    [{isAd: true, adPayment: 1.1, adPaymentPeriod: 'bleh'}, 'Unable to parse adPaymentPeriod'],
  ])('Cannot add post with ad params: %p', async ({isAd, adPayment, adPaymentPeriod}, errorMsg) => {
    const postId = uuidv4()
    await client
      .mutate({
        mutation: mutations.addPost,
        variables: {postId, imageData, isAd, adPayment, adPaymentPeriod},
        errorPolicy: 'all',
      })
      .then(({errors}) => {
        expect(errors).toHaveLength(1)
        expect(errors[0].message).toMatch(/^ClientError: /)
        expect(errors[0].message).toContain(errorMsg)
      })
    await sleep()
    await client.query({query: queries.post, variables: {postId}}).then(({data}) => expect(data.post).toBeNull())
  })

  test.each([{}, {adPaymentPeriod: 'P1D'}])(
    'Can add an ad post with optional ad params: %p',
    async ({adPaymentPeriod}) => {
      const postId = uuidv4()
      const adPayment = Number.parseFloat(Number(Math.random() * 1000).toFixed(6))
      await client
        .mutate({
          mutation: mutations.addPost,
          variables: {postId, imageData, isAd: true, adPayment, adPaymentPeriod},
        })
        .then(({data}) => expect(data.addPost.postId).toBe(postId))
      await eventually(async () => {
        const {data} = await client.query({query: queries.post, variables: {postId}})
        expect(data.post.postId).toBe(postId)
        expect(data.post.postStatus).toBe('COMPLETED')
        expect(data.post.adStatus).toBe('PENDING')
        expect(data.post.adPayment).toBe(adPayment)
        expect(data.post.adPaymentPeriod).toBe(adPaymentPeriod || null)
      })
    },
  )
})

describe('Effect of User.adsDisabled on visibility of ads & normal posts', () => {
  let ourClient, ourUserId
  let theirClient, theirUserId
  const ourAdPostId = uuidv4()
  const ourNormalPostId = uuidv4()
  const theirAdPostId = uuidv4()
  const theirNormalPostId = uuidv4()

  beforeAll(async () => {
    await loginCache.clean()
    ;({client: ourClient, userId: ourUserId} = await loginCache.getCleanLogin())
    ;({client: theirClient, userId: theirUserId} = await loginCache.getCleanLogin())
    // we add one ad and one normal post
    await ourClient.mutate({mutation: mutations.addPost, variables: {postId: ourNormalPostId, imageData}})
    await ourClient.mutate({
      mutation: mutations.addPost,
      variables: {postId: ourAdPostId, imageData, isAd: true, adPayment: 0},
    })
    // they add one ad and one normal post
    await theirClient.mutate({mutation: mutations.addPost, variables: {postId: theirNormalPostId, imageData}})
    await theirClient.mutate({
      mutation: mutations.addPost,
      variables: {postId: theirAdPostId, imageData, isAd: true, adPayment: 0},
    })
    // they disable ads
    await theirClient.mutate({mutation: mutations.setUserMentalHealthSettings, variables: {adsDisabled: true}})
  })

  test('Successful setup', async () => {
    // we have ads enabled, the default
    await eventually(async () => {
      const {data} = await ourClient.query({query: queries.self})
      expect(data.self.adsDisabled).toBe(false)
    })
    // they have ads disabled
    await eventually(async () => {
      const {data} = await theirClient.query({query: queries.self})
      expect(data.self.adsDisabled).toBe(true)
    })
    // our posts completed
    await eventually(async () => {
      const {data} = await ourClient.query({query: queries.post, variables: {postId: ourNormalPostId}})
      expect(data.post.postId).toBe(ourNormalPostId)
      expect(data.post.postStatus).toBe('COMPLETED')
      expect(data.post.adStatus).toBe('NOT_AD')
    })
    await eventually(async () => {
      const {data} = await ourClient.query({query: queries.post, variables: {postId: ourAdPostId}})
      expect(data.post.postId).toBe(ourAdPostId)
      expect(data.post.postStatus).toBe('COMPLETED')
      expect(data.post.adStatus).toBe('PENDING')
    })
    // their posts completed
    await eventually(async () => {
      const {data} = await theirClient.query({query: queries.post, variables: {postId: theirNormalPostId}})
      expect(data.post.postId).toBe(theirNormalPostId)
      expect(data.post.postStatus).toBe('COMPLETED')
      expect(data.post.adStatus).toBe('NOT_AD')
    })
    await eventually(async () => {
      const {data} = await theirClient.query({query: queries.post, variables: {postId: theirAdPostId}})
      expect(data.post.postId).toBe(theirAdPostId)
      expect(data.post.postStatus).toBe('COMPLETED')
      expect(data.post.adStatus).toBe('PENDING')
    })
  })

  test('With User.adsDisabled=False, user sees their own ads and non-ads', async () => {
    await ourClient
      .query({query: queries.userPosts, variables: {userId: ourUserId}})
      .then(({data}) => expect(data.user.posts.items).toHaveLength(2))
    await ourClient
      .query({query: queries.post, variables: {postId: ourNormalPostId}})
      .then(({data}) => expect(data.post.postId).toBe(ourNormalPostId))
    await ourClient
      .query({query: queries.post, variables: {postId: ourAdPostId}})
      .then(({data}) => expect(data.post.postId).toBe(ourAdPostId))
  })

  test('With User.adsDisabled=False, user sees non-ads and ads of other users', async () => {
    await ourClient
      .query({query: queries.userPosts, variables: {userId: theirUserId}})
      .then(({data}) => expect(data.user.posts.items).toHaveLength(2))
    await ourClient
      .query({query: queries.post, variables: {postId: theirNormalPostId}})
      .then(({data}) => expect(data.post.postId).toBe(theirNormalPostId))
    await ourClient
      .query({query: queries.post, variables: {postId: theirAdPostId}})
      .then(({data}) => expect(data.post.postId).toBe(theirAdPostId))
  })

  test('With User.adsDisabled=True, user sees their own ads and non-ads', async () => {
    await theirClient
      .query({query: queries.userPosts, variables: {userId: theirUserId}})
      .then(({data}) => expect(data.user.posts.items).toHaveLength(2))
    await theirClient
      .query({query: queries.post, variables: {postId: theirNormalPostId}})
      .then(({data}) => expect(data.post.postId).toBe(theirNormalPostId))
    await theirClient
      .query({query: queries.post, variables: {postId: theirAdPostId}})
      .then(({data}) => expect(data.post.postId).toBe(theirAdPostId))
  })

  test('With User.adsDisabled=True, user sees non-ads of other users but not ads', async () => {
    await theirClient.query({query: queries.userPosts, variables: {userId: ourUserId}}).then(({data}) => {
      expect(data.user.posts.items).toHaveLength(1)
      expect(data.user.posts.items[0].postId).toBe(ourNormalPostId)
    })
    await theirClient
      .query({query: queries.post, variables: {postId: ourNormalPostId}})
      .then(({data}) => expect(data.post.postId).toBe(ourNormalPostId))
    await theirClient
      .query({query: queries.post, variables: {postId: ourAdPostId}})
      .then(({data}) => expect(data.post).toBeNull())
  })
})
