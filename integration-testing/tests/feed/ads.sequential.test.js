/**
 * This test suite cannot run in parrallel with others because it
 * depends on global state - namely the 'real' user.
 */
const {v4: uuidv4} = require('uuid')

const {cognito, eventually, generateRandomJpeg} = require('../../utils')
const realUser = require('../../utils/real-user')
const {mutations, queries} = require('../../schema')

const imageBytes = generateRandomJpeg(8, 8)
const imageData = new Buffer.from(imageBytes).toString('base64')
const loginCache = new cognito.AppSyncLoginCache()
let realLogin

beforeAll(async () => {
  realLogin = await realUser.getLogin()
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})
afterAll(async () => {
  await realUser.resetLogin()
  await loginCache.reset()
})

describe('Ad injected into feed', () => {
  const [adid1, adid2] = [uuidv4(), uuidv4()]
  const [pid1, pid2, pid3] = [uuidv4(), uuidv4(), uuidv4()]
  let client1, client2, realClient
  let userId1

  beforeAll(async () => {
    await loginCache.clean()
    await realUser.cleanLogin()
    ;({client: realClient} = await realLogin)
    ;({client: client1, userId: userId1} = await loginCache.getCleanLogin())
    ;({client: client2} = await loginCache.getCleanLogin())
    // client1 adds an ad, which the real user approves
    await client1.mutate({
      mutation: mutations.addPost,
      variables: {postId: adid1, imageData, isAd: true, adPayment: 0.01},
    })
    await eventually(async () => {
      const {data} = await client1.query({query: queries.post, variables: {postId: adid1}})
      expect(data.post.postId).toBe(adid1)
      expect(data.post.postStatus).toBe('COMPLETED')
    })
    await realClient.mutate({mutation: mutations.approveAdPost, variables: {postId: adid1}})
    await eventually(async () => {
      const {data} = await client1.query({query: queries.post, variables: {postId: adid1}})
      expect(data.post.postId).toBe(adid1)
      expect(data.post.adStatus).toBe('ACTIVE')
    })
  })

  test('user with empty feed does does not get the ad', async () => {
    await eventually(async () => {
      const {data} = await client2.query({query: queries.selfFeed})
      expect(data.self.feed.items).toHaveLength(0)
    })
  })

  describe('user with one post in feed', () => {
    beforeAll(async () => {
      await client2.mutate({mutation: mutations.addPost, variables: {postId: pid1, imageData}})
      await eventually(async () => {
        const {data} = await client2.query({query: queries.post, variables: {postId: pid1}})
        expect(data.post.postId).toBe(pid1)
        expect(data.post.postStatus).toBe('COMPLETED')
      })
    })

    test('does does not get the ad', async () => {
      await eventually(async () => {
        const {data} = await client2.query({query: queries.selfFeed})
        expect(data.self.feed.items).toHaveLength(1)
        expect(data.self.feed.items[0].postId).toBe(pid1)
      })
    })
  })

  describe('user with two posts in feed', () => {
    beforeAll(async () => {
      await client2.mutate({mutation: mutations.addPost, variables: {postId: pid2, imageData}})
      await eventually(async () => {
        const {data} = await client2.query({query: queries.post, variables: {postId: pid2}})
        expect(data.post.postId).toBe(pid2)
        expect(data.post.postStatus).toBe('COMPLETED')
      })
    })

    test('when querying with limit 2 or less, does not get the ad', async () => {
      await eventually(async () => {
        const {data} = await client2.query({query: queries.selfFeed, variables: {limit: 2}})
        expect(data.self.feed.items).toHaveLength(2)
        expect(data.self.feed.items[0].postId).toBe(pid2)
        expect(data.self.feed.items[1].postId).toBe(pid1)
      })
    })

    test('when querying with limit 3 or more, gets the ad in the correct place', async () => {
      await eventually(async () => {
        const {data} = await client2.query({query: queries.selfFeed, variables: {limit: 3}})
        expect(data.self.feed.items).toHaveLength(3)
        expect(data.self.feed.items[0].postId).toBe(pid2)
        expect(data.self.feed.items[1].postId).toBe(adid1)
        expect(data.self.feed.items[2].postId).toBe(pid1)
      })
    })
  })

  describe('user with three posts in feed', () => {
    beforeAll(async () => {
      await client2.mutate({mutation: mutations.addPost, variables: {postId: pid3, imageData}})
      await eventually(async () => {
        const {data} = await client2.query({query: queries.post, variables: {postId: pid3}})
        expect(data.post.postId).toBe(pid3)
        expect(data.post.postStatus).toBe('COMPLETED')
      })
    })

    test('when querying with limit 2 or less, does not get the ad', async () => {
      await eventually(async () => {
        const {data} = await client2.query({query: queries.selfFeed, variables: {limit: 2}})
        expect(data.self.feed.items).toHaveLength(2)
        expect(data.self.feed.items[0].postId).toBe(pid3)
        expect(data.self.feed.items[1].postId).toBe(pid2)
      })
    })

    test('when querying with limit 3 or more, gets the ad in the correct place', async () => {
      await eventually(async () => {
        const {data} = await client2.query({query: queries.selfFeed, variables: {limit: 3}})
        expect(data.self.feed.items).toHaveLength(3)
        expect(data.self.feed.items[0].postId).toBe(pid3)
        expect(data.self.feed.items[1].postId).toBe(adid1)
        expect(data.self.feed.items[2].postId).toBe(pid2)
      })
      await eventually(async () => {
        const {data} = await client2.query({query: queries.selfFeed})
        expect(data.self.feed.items).toHaveLength(4)
        expect(data.self.feed.items[0].postId).toBe(pid3)
        expect(data.self.feed.items[1].postId).toBe(adid1)
        expect(data.self.feed.items[2].postId).toBe(pid2)
        expect(data.self.feed.items[3].postId).toBe(pid1)
      })
    })
  })

  describe('user with ads disabled and has posts in their feed', () => {
    beforeAll(async () => {
      await client2.mutate({mutation: mutations.setUserMentalHealthSettings, variables: {adsDisabled: true}})
      await eventually(async () => {
        const {data} = await client2.query({query: queries.self})
        expect(data.self.adsDisabled).toBe(true)
      })
    })

    test('does not get the ad', async () => {
      await eventually(async () => {
        const {data} = await client2.query({query: queries.selfFeed})
        expect(data.self.feed.items).toHaveLength(3)
        expect(data.self.feed.items[0].postId).toBe(pid3)
        expect(data.self.feed.items[1].postId).toBe(pid2)
        expect(data.self.feed.items[2].postId).toBe(pid1)
      })
    })
  })

  describe('user who recently enabled ads and has posts in their feed', () => {
    beforeAll(async () => {
      await client2.mutate({mutation: mutations.setUserMentalHealthSettings, variables: {adsDisabled: false}})
      await eventually(async () => {
        const {data} = await client2.query({query: queries.self})
        expect(data.self.adsDisabled).toBe(false)
      })
    })

    test('gets the ad', async () => {
      await eventually(async () => {
        const {data} = await client2.query({query: queries.selfFeed})
        expect(data.self.feed.items).toHaveLength(4)
        expect(data.self.feed.items[0].postId).toBe(pid3)
        expect(data.self.feed.items[1].postId).toBe(adid1)
        expect(data.self.feed.items[2].postId).toBe(pid2)
        expect(data.self.feed.items[3].postId).toBe(pid1)
      })
    })
  })

  describe('user with an ad in their feed already', () => {
    beforeAll(async () => {
      await client2.mutate({
        mutation: mutations.addPost,
        variables: {postId: adid2, imageData, isAd: true, adPayment: 0.01},
      })
      await eventually(async () => {
        const {data} = await client2.query({query: queries.post, variables: {postId: adid2}})
        expect(data.post.postId).toBe(adid2)
        expect(data.post.postStatus).toBe('COMPLETED')
      })
      await realClient.mutate({mutation: mutations.approveAdPost, variables: {postId: adid2}})
      await eventually(async () => {
        const {data} = await client2.query({query: queries.post, variables: {postId: adid2}})
        expect(data.post.postId).toBe(adid2)
        expect(data.post.adStatus).toBe('ACTIVE')
      })
    })

    test('gets the ad already in their feed, does not get another ad injected', async () => {
      await eventually(async () => {
        const {data} = await client2.query({query: queries.selfFeed})
        expect(data.self.feed.items).toHaveLength(4)
        expect(data.self.feed.items[0].postId).toBe(adid2)
        expect(data.self.feed.items[1].postId).toBe(pid3)
        expect(data.self.feed.items[2].postId).toBe(pid2)
        expect(data.self.feed.items[3].postId).toBe(pid1)
      })
    })
  })

  describe('user that follows a user that posted an ad', () => {
    beforeAll(async () => {
      await client2.mutate({mutation: mutations.followUser, variables: {userId: userId1}})
      await eventually(async () => {
        const {data} = await client2.query({query: queries.self})
        expect(data.self.followedUsers.items).toHaveLength(1)
        expect(data.self.followedUsers.items[0].userId).toBe(userId1)
      })
    })

    test('sees all ads already in their feed, does not get another ad injected', async () => {
      await eventually(async () => {
        const {data} = await client2.query({query: queries.selfFeed})
        expect(data.self.feed.items).toHaveLength(5)
        expect(data.self.feed.items[0].postId).toBe(adid2)
        expect(data.self.feed.items[1].postId).toBe(pid3)
        expect(data.self.feed.items[2].postId).toBe(pid2)
        expect(data.self.feed.items[3].postId).toBe(pid1)
        expect(data.self.feed.items[4].postId).toBe(adid1)
      })
    })
  })

  describe('user with adsDisabled = True that follows a user that posted an ad', () => {
    beforeAll(async () => {
      await client2.mutate({mutation: mutations.setUserMentalHealthSettings, variables: {adsDisabled: true}})
      await eventually(async () => {
        const {data} = await client2.query({query: queries.self})
        expect(data.self.adsDisabled).toBe(true)
      })
    })

    test('does not see any other users ads in their feed, only their own ads', async () => {
      await eventually(async () => {
        const {data} = await client2.query({query: queries.selfFeed})
        expect(data.self.feed.items).toHaveLength(4)
        expect(data.self.feed.items[0].postId).toBe(adid2)
        expect(data.self.feed.items[1].postId).toBe(pid3)
        expect(data.self.feed.items[2].postId).toBe(pid2)
        expect(data.self.feed.items[3].postId).toBe(pid1)
      })
    })
  })
})

describe('Targeting of injected ads', () => {
  const [adid1, adid2] = [uuidv4(), uuidv4()]
  const [pid1, pid2, pid3] = [uuidv4(), uuidv4(), uuidv4()]
  let client1, client2, realClient

  describe('user with full feed and ads of their own', () => {
    beforeAll(async () => {
      await loginCache.clean()
      await realUser.cleanLogin()
      ;({client: realClient} = await realLogin)
      ;({client: client1} = await loginCache.getCleanLogin())
      ;({client: client2} = await loginCache.getCleanLogin())
      // client1 adds an ad, which the real user approves
      await client1.mutate({
        mutation: mutations.addPost,
        variables: {postId: adid1, imageData, isAd: true, adPayment: 0.01},
      })
      await eventually(async () => {
        const {data} = await client1.query({query: queries.post, variables: {postId: adid1}})
        expect(data.post.postId).toBe(adid1)
        expect(data.post.postStatus).toBe('COMPLETED')
      })
      await realClient.mutate({mutation: mutations.approveAdPost, variables: {postId: adid1}})
      await eventually(async () => {
        const {data} = await client1.query({query: queries.post, variables: {postId: adid1}})
        expect(data.post.postId).toBe(adid1)
        expect(data.post.adStatus).toBe('ACTIVE')
      })
      //client 1 adds three posts
      await client1.mutate({mutation: mutations.addPost, variables: {postId: pid1, imageData}})
      await eventually(async () => {
        const {data} = await client1.query({query: queries.post, variables: {postId: pid1}})
        expect(data.post.postId).toBe(pid1)
        expect(data.post.postStatus).toBe('COMPLETED')
      })
      await client1.mutate({mutation: mutations.addPost, variables: {postId: pid2, imageData}})
      await eventually(async () => {
        const {data} = await client1.query({query: queries.post, variables: {postId: pid2}})
        expect(data.post.postId).toBe(pid2)
        expect(data.post.postStatus).toBe('COMPLETED')
      })
      await client1.mutate({mutation: mutations.addPost, variables: {postId: pid3, imageData}})
      await eventually(async () => {
        const {data} = await client1.query({query: queries.post, variables: {postId: pid3}})
        expect(data.post.postId).toBe(pid3)
        expect(data.post.postStatus).toBe('COMPLETED')
      })
    })

    test('does not get their own ads injected into their feed', async () => {
      await eventually(async () => {
        const {data} = await client1.query({query: queries.selfFeed, variables: {limit: 3}})
        expect(data.self.feed.items).toHaveLength(2) // would be nice if all three posts were returned
        expect(data.self.feed.items[0].postId).toBe(pid3)
        expect(data.self.feed.items[1].postId).toBe(pid2)
      })
    })

    describe('with an active ad from another user', () => {
      beforeAll(async () => {
        // client2 adds an ad, which the real user approves
        await client2.mutate({
          mutation: mutations.addPost,
          variables: {postId: adid2, imageData, isAd: true, adPayment: 0.01},
        })
        await eventually(async () => {
          const {data} = await client2.query({query: queries.post, variables: {postId: adid2}})
          expect(data.post.postId).toBe(adid2)
          expect(data.post.postStatus).toBe('COMPLETED')
        })
        await realClient.mutate({mutation: mutations.approveAdPost, variables: {postId: adid2}})
        await eventually(async () => {
          const {data} = await client2.query({query: queries.post, variables: {postId: adid2}})
          expect(data.post.postId).toBe(adid2)
          expect(data.post.adStatus).toBe('ACTIVE')
        })
      })

      test('user does get ads of other users injected', async () => {
        const {data} = await client1.query({query: queries.selfFeed, variables: {limit: 3}})
        expect(data.self.feed.items).toHaveLength(3)
        expect(data.self.feed.items[0].postId).toBe(pid3)
        expect(data.self.feed.items[1].postId).toBe(adid2)
        expect(data.self.feed.items[2].postId).toBe(pid2)
      })
    })
  })
})

describe('Post lifecycle and ads injected into feed', () => {
  const adid1 = uuidv4()
  const [pid1, pid2] = [uuidv4(), uuidv4()]
  let client1, client2, realClient

  beforeAll(async () => {
    await loginCache.clean()
    await realUser.cleanLogin()
    ;({client: realClient} = await realLogin)
    ;({client: client1} = await loginCache.getCleanLogin())
    ;({client: client2} = await loginCache.getCleanLogin())
    // client2 ads to posts to fill up their feed
    await client2.mutate({mutation: mutations.addPost, variables: {postId: pid1, imageData}})
    await eventually(async () => {
      const {data} = await client2.query({query: queries.post, variables: {postId: pid1}})
      expect(data.post.postId).toBe(pid1)
      expect(data.post.postStatus).toBe('COMPLETED')
    })
    await client2.mutate({mutation: mutations.addPost, variables: {postId: pid2, imageData}})
    await eventually(async () => {
      const {data} = await client2.query({query: queries.post, variables: {postId: pid2}})
      expect(data.post.postId).toBe(pid2)
      expect(data.post.postStatus).toBe('COMPLETED')
    })
  })

  describe('ad with postStatus COMPLETED', () => {
    beforeAll(async () => {
      // client1 adds an ad, which the real user approves
      await client1.mutate({
        mutation: mutations.addPost,
        variables: {postId: adid1, imageData, isAd: true, adPayment: 0.01},
      })
      await eventually(async () => {
        const {data} = await client1.query({query: queries.post, variables: {postId: adid1}})
        expect(data.post.postId).toBe(adid1)
        expect(data.post.postStatus).toBe('COMPLETED')
      })
      await realClient.mutate({mutation: mutations.approveAdPost, variables: {postId: adid1}})
      await eventually(async () => {
        const {data} = await client1.query({query: queries.post, variables: {postId: adid1}})
        expect(data.post.postId).toBe(adid1)
        expect(data.post.adStatus).toBe('ACTIVE')
      })
    })

    test('is injected into feed', async () => {
      await eventually(async () => {
        const {data} = await client2.query({query: queries.selfFeed})
        expect(data.self.feed.items).toHaveLength(3)
        expect(data.self.feed.items[0].postId).toBe(pid2)
        expect(data.self.feed.items[1].postId).toBe(adid1)
        expect(data.self.feed.items[2].postId).toBe(pid1)
      })
    })
  })

  describe('ad with postStatus ARCHIVED', () => {
    beforeAll(async () => {
      // client1 archives their ad post
      await client1.mutate({mutation: mutations.archivePost, variables: {postId: adid1}})
      await eventually(async () => {
        const {data} = await client1.query({query: queries.post, variables: {postId: adid1}})
        expect(data.post.postId).toBe(adid1)
        expect(data.post.postStatus).toBe('ARCHIVED')
      })
    })

    test('is not injected into feed', async () => {
      await eventually(async () => {
        const {data} = await client2.query({query: queries.selfFeed})
        expect(data.self.feed.items).toHaveLength(2)
        expect(data.self.feed.items[0].postId).toBe(pid2)
        expect(data.self.feed.items[1].postId).toBe(pid1)
      })
    })
  })

  describe('ad recently restored back to postStatus COMPLETED', () => {
    beforeAll(async () => {
      // client1 restores their ad post
      await client1.mutate({mutation: mutations.restoreArchivedPost, variables: {postId: adid1}})
      await eventually(async () => {
        const {data} = await client1.query({query: queries.post, variables: {postId: adid1}})
        expect(data.post.postId).toBe(adid1)
        expect(data.post.postStatus).toBe('COMPLETED')
      })
    })

    test('is injected into feed', async () => {
      await eventually(async () => {
        const {data} = await client2.query({query: queries.selfFeed})
        expect(data.self.feed.items).toHaveLength(3)
        expect(data.self.feed.items[0].postId).toBe(pid2)
        expect(data.self.feed.items[1].postId).toBe(adid1)
        expect(data.self.feed.items[2].postId).toBe(pid1)
      })
    })
  })

  describe('ad recently that has been deleted', () => {
    beforeAll(async () => {
      // client1 deletes their ad post
      await client1.mutate({mutation: mutations.deletePost, variables: {postId: adid1}})
      await eventually(async () => {
        const {data} = await client1.query({query: queries.post, variables: {postId: adid1}})
        expect(data.post).toBeNull()
      })
    })

    test('is not injected into feed', async () => {
      await eventually(async () => {
        const {data} = await client2.query({query: queries.selfFeed})
        expect(data.self.feed.items).toHaveLength(2)
        expect(data.self.feed.items[0].postId).toBe(pid2)
        expect(data.self.feed.items[1].postId).toBe(pid1)
      })
    })
  })
})

describe('Ads injection into feed is LRU', () => {
  const [adid1, adid2, adid3] = [uuidv4(), uuidv4(), uuidv4()]
  const [pid1, pid2] = [uuidv4(), uuidv4()]
  let client1, client2, realClient

  beforeAll(async () => {
    await loginCache.clean()
    await realUser.cleanLogin()
    ;({client: realClient} = await realLogin)
    ;({client: client1} = await loginCache.getCleanLogin())
    ;({client: client2} = await loginCache.getCleanLogin())
    // client2 ads to posts to fill up their feed
    await client2.mutate({mutation: mutations.addPost, variables: {postId: pid1, imageData}})
    await eventually(async () => {
      const {data} = await client2.query({query: queries.post, variables: {postId: pid1}})
      expect(data.post.postId).toBe(pid1)
      expect(data.post.postStatus).toBe('COMPLETED')
    })
    await client2.mutate({mutation: mutations.addPost, variables: {postId: pid2, imageData}})
    await eventually(async () => {
      const {data} = await client2.query({query: queries.post, variables: {postId: pid2}})
      expect(data.post.postId).toBe(pid2)
      expect(data.post.postStatus).toBe('COMPLETED')
    })
    // client1 adds an ad, which the real user approves
    await client1.mutate({
      mutation: mutations.addPost,
      variables: {postId: adid1, postType: 'TEXT_ONLY', text: '-', isAd: true, adPayment: 0.01},
    })
    await eventually(async () => {
      const {data} = await client1.query({query: queries.post, variables: {postId: adid1}})
      expect(data.post.postId).toBe(adid1)
      expect(data.post.postStatus).toBe('COMPLETED')
    })
    await realClient.mutate({mutation: mutations.approveAdPost, variables: {postId: adid1}})
    await eventually(async () => {
      const {data} = await client1.query({query: queries.post, variables: {postId: adid1}})
      expect(data.post.postId).toBe(adid1)
      expect(data.post.adStatus).toBe('ACTIVE')
    })
    // client1 adds another ad, which the real user approves
    await client1.mutate({
      mutation: mutations.addPost,
      variables: {postId: adid2, postType: 'TEXT_ONLY', text: '-', isAd: true, adPayment: 0.01},
    })
    await eventually(async () => {
      const {data} = await client1.query({query: queries.post, variables: {postId: adid2}})
      expect(data.post.postId).toBe(adid2)
      expect(data.post.postStatus).toBe('COMPLETED')
    })
    await realClient.mutate({mutation: mutations.approveAdPost, variables: {postId: adid2}})
    await eventually(async () => {
      const {data} = await client1.query({query: queries.post, variables: {postId: adid2}})
      expect(data.post.postId).toBe(adid2)
      expect(data.post.adStatus).toBe('ACTIVE')
    })
  })

  describe('without having viewed either ad', () => {
    test('sort order is indeterminant', async () => {
      await eventually(async () => {
        const {data} = await client2.query({query: queries.selfFeed})
        expect(data.self.feed.items).toHaveLength(3)
        expect(data.self.feed.items[0].postId).toBe(pid2)
        expect([adid1, adid2]).toContain(data.self.feed.items[1].postId)
        expect(data.self.feed.items[2].postId).toBe(pid1)
      })
    })
  })

  describe('having viewed one of the two ads', () => {
    beforeAll(async () => {
      await client2.mutate({mutation: mutations.reportPostViews, variables: {postIds: [adid2]}})
    })

    test('the other is served', async () => {
      await eventually(async () => {
        const {data} = await client2.query({query: queries.selfFeed})
        expect(data.self.feed.items).toHaveLength(3)
        expect(data.self.feed.items[0].postId).toBe(pid2)
        expect(data.self.feed.items[1].postId).toBe(adid1)
        expect(data.self.feed.items[2].postId).toBe(pid1)
      })
    })
  })

  describe('having viewed both of the two ads', () => {
    beforeAll(async () => {
      await client2.mutate({mutation: mutations.reportPostViews, variables: {postIds: [adid1]}})
    })

    test('the least recently viewed one is served', async () => {
      await eventually(async () => {
        const {data} = await client2.query({query: queries.selfFeed})
        expect(data.self.feed.items).toHaveLength(3)
        expect(data.self.feed.items[0].postId).toBe(pid2)
        expect(data.self.feed.items[1].postId).toBe(adid2)
        expect(data.self.feed.items[2].postId).toBe(pid1)
      })
    })
  })

  describe('with another unviewed ad being created', () => {
    beforeAll(async () => {
      // client1 adds another ad, which the real user approves
      await client1.mutate({
        mutation: mutations.addPost,
        variables: {postId: adid3, postType: 'TEXT_ONLY', text: '-', isAd: true, adPayment: 0.01},
      })
      await eventually(async () => {
        const {data} = await client1.query({query: queries.post, variables: {postId: adid3}})
        expect(data.post.postId).toBe(adid3)
        expect(data.post.postStatus).toBe('COMPLETED')
      })
      await realClient.mutate({mutation: mutations.approveAdPost, variables: {postId: adid3}})
      await eventually(async () => {
        const {data} = await client1.query({query: queries.post, variables: {postId: adid3}})
        expect(data.post.postId).toBe(adid3)
        expect(data.post.adStatus).toBe('ACTIVE')
      })
    })

    test('the never-viewed ad is served', async () => {
      await eventually(async () => {
        const {data} = await client2.query({query: queries.selfFeed})
        expect(data.self.feed.items).toHaveLength(3)
        expect(data.self.feed.items[0].postId).toBe(pid2)
        expect(data.self.feed.items[1].postId).toBe(adid3)
        expect(data.self.feed.items[2].postId).toBe(pid1)
      })
    })
  })

  describe('having viewed all of the three ads', () => {
    beforeAll(async () => {
      await client2.mutate({mutation: mutations.reportPostViews, variables: {postIds: [adid3]}})
    })

    test('the least recently viewed one is served', async () => {
      await eventually(async () => {
        const {data} = await client2.query({query: queries.selfFeed})
        expect(data.self.feed.items).toHaveLength(3)
        expect(data.self.feed.items[0].postId).toBe(pid2)
        expect(data.self.feed.items[1].postId).toBe(adid2)
        expect(data.self.feed.items[2].postId).toBe(pid1)
      })
    })

    test('if no more views are reported, the same least recently viewed one is served again', async () => {
      await eventually(async () => {
        const {data} = await client2.query({query: queries.selfFeed})
        expect(data.self.feed.items).toHaveLength(3)
        expect(data.self.feed.items[0].postId).toBe(pid2)
        expect(data.self.feed.items[1].postId).toBe(adid2)
        expect(data.self.feed.items[2].postId).toBe(pid1)
      })
    })
  })

  describe('having reported another view on an ad not the most recently viewed', () => {
    beforeAll(async () => {
      await client2.mutate({mutation: mutations.reportPostViews, variables: {postIds: [adid1]}})
    })

    test('the least recently viewed one does not change and is served', async () => {
      await eventually(async () => {
        const {data} = await client2.query({query: queries.selfFeed})
        expect(data.self.feed.items).toHaveLength(3)
        expect(data.self.feed.items[0].postId).toBe(pid2)
        expect(data.self.feed.items[1].postId).toBe(adid2)
        expect(data.self.feed.items[2].postId).toBe(pid1)
      })
    })
  })
})
