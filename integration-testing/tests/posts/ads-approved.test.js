import {v4 as uuidv4} from 'uuid'

import {cognito, eventually, generateRandomJpeg, sleep} from '../../utils'
import {realUser} from '../../utils'
import {mutations, queries} from '../../schema'

const imageBytes = generateRandomJpeg(8, 8)
const imageData = new Buffer.from(imageBytes).toString('base64')
const loginCache = new cognito.AppSyncLoginCache()
let realClient

beforeAll(async () => {
  ;({client: realClient} = await realUser.getLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})
afterAll(async () => {
  await loginCache.reset()
})

describe('Approving an ad post', () => {
  const postIdAd = uuidv4()
  const postIdAdNotCompleted = uuidv4()
  const postIdNonAd = uuidv4()
  let client

  beforeAll(async () => {
    await loginCache.clean()
    ;({client} = await loginCache.getCleanLogin())
    await client.mutate({
      mutation: mutations.addPost,
      variables: {postId: postIdAd, imageData, isAd: true, adPayment: 0.01},
    })
    await client.mutate({
      mutation: mutations.addPost,
      variables: {postId: postIdAdNotCompleted, isAd: true, adPayment: 0.01},
    })
    await client.mutate({mutation: mutations.addPost, variables: {postId: postIdNonAd, imageData}})
  })

  test('Setup success', async () => {
    await eventually(async () => {
      const {data} = await client.query({query: queries.post, variables: {postId: postIdAd}})
      expect(data.post.postId).toBe(postIdAd)
      expect(data.post.postStatus).toBe('COMPLETED')
      expect(data.post.adStatus).toBe('PENDING')
    })
    await client.query({query: queries.post, variables: {postId: postIdAdNotCompleted}}).then(({data}) => {
      expect(data.post.postId).toBe(postIdAdNotCompleted)
      expect(data.post.postStatus).toBe('PENDING')
      expect(data.post.adStatus).toBe('PENDING')
    })
    await eventually(async () => {
      const {data} = await client.query({query: queries.post, variables: {postId: postIdNonAd}})
      expect(data.post.postId).toBe(postIdNonAd)
      expect(data.post.postStatus).toBe('COMPLETED')
      expect(data.post.adStatus).toBe('NOT_AD')
    })
  })

  test('Normal user cannot approve ad post', async () => {
    await client
      .mutate({mutation: mutations.approveAdPost, variables: {postId: postIdAd}, errorPolicy: 'all'})
      .then(({errors}) => {
        expect(errors).toHaveLength(1)
        expect(errors[0].message).toMatch(/^ClientError: /)
        expect(errors[0].message).toMatch(/User .* may not approve ads/)
      })
    await sleep()
    await client.query({query: queries.post, variables: {postId: postIdAd}}).then(({data}) => {
      expect(data.post.postId).toBe(postIdAd)
      expect(data.post.adStatus).toBe('PENDING')
    })
  })

  describe('a REAL admin, such as the REAL user', () => {
    test('can approve an ad post', async () => {
      await realClient
        .mutate({mutation: mutations.approveAdPost, variables: {postId: postIdAd}})
        .then(({data}) => expect(data.approveAdPost.adStatus).toBe('ACTIVE'))
      await eventually(async () => {
        const {data} = await client.query({query: queries.post, variables: {postId: postIdAd}})
        expect(data.post.postId).toBe(postIdAd)
        expect(data.post.adStatus).toBe('ACTIVE')
      })
    })

    test('cannot double approve an ad post', async () => {
      await realClient
        .mutate({mutation: mutations.approveAdPost, variables: {postId: postIdAd}, errorPolicy: 'all'})
        .then(({errors}) => {
          expect(errors).toHaveLength(1)
          expect(errors[0].message).toMatch(/^ClientError: /)
          expect(errors[0].message).toMatch(/Cannot approve post .* with adStatus `ACTIVE`/)
        })
    })

    test('cannot approve a non-COMPLETED ad post', async () => {
      await realClient
        .mutate({
          mutation: mutations.approveAdPost,
          variables: {postId: postIdAdNotCompleted},
          errorPolicy: 'all',
        })
        .then(({errors}) => {
          expect(errors).toHaveLength(1)
          expect(errors[0].message).toMatch(/^ClientError: /)
          expect(errors[0].message).toMatch(/Cannot approve post .* with status `PENDING`/)
        })
    })

    test('cannot approve a non-ad post', async () => {
      await realClient
        .mutate({mutation: mutations.approveAdPost, variables: {postId: postIdNonAd}, errorPolicy: 'all'})
        .then(({errors}) => {
          expect(errors).toHaveLength(1)
          expect(errors[0].message).toMatch(/^ClientError: /)
          expect(errors[0].message).toMatch(/Cannot approve post .* with adStatus `NOT_AD`/)
        })
    })

    test('cannot approve a post that does not exist', async () => {
      await realClient
        .mutate({mutation: mutations.approveAdPost, variables: {postId: uuidv4()}, errorPolicy: 'all'})
        .then(({errors}) => {
          expect(errors).toHaveLength(1)
          expect(errors[0].message).toMatch(/^ClientError: /)
          expect(errors[0].message).toMatch(/Post .* does not exist/)
        })
    })
  })
})

describe('An ad post', () => {
  const postId = uuidv4()
  let client

  beforeAll(async () => {
    await loginCache.clean()
    ;({client} = await loginCache.getCleanLogin())
    await client.mutate({
      mutation: mutations.addPost,
      variables: {postId, imageData, isAd: true, adPayment: 0.01},
    })
  })

  test('Setup', async () => {
    await eventually(async () => {
      const {data} = await client.query({query: queries.post, variables: {postId}})
      expect(data.post.postId).toBe(postId)
      expect(data.post.postStatus).toBe('COMPLETED')
      expect(data.post.adStatus).toBe('PENDING')
    })
  })

  describe('Which is approved', () => {
    beforeAll(async () => {
      await realClient.mutate({mutation: mutations.approveAdPost, variables: {postId}})
    })

    test('Setup', async () => {
      await eventually(async () => {
        const {data} = await client.query({query: queries.post, variables: {postId}})
        expect(data.post.postId).toBe(postId)
        expect(data.post.adStatus).toBe('ACTIVE')
      })
    })

    test('Archiving the post transitions it to adStatus INACTIVE', async () => {
      await client.mutate({mutation: mutations.archivePost, variables: {postId}}).then(({data}) => {
        expect(data.archivePost.postId).toBe(postId)
        expect(data.archivePost.postStatus).toBe('ARCHIVED')
      })
      await eventually(async () => {
        const {data} = await client.query({query: queries.post, variables: {postId}})
        expect(data.post.postId).toBe(postId)
        expect(data.post.adStatus).toBe('INACTIVE')
      })
    })

    test('Restoring the post transitions it to adStatus ACTIVE', async () => {
      await client.mutate({mutation: mutations.restoreArchivedPost, variables: {postId}}).then(({data}) => {
        expect(data.restoreArchivedPost.postId).toBe(postId)
        expect(data.restoreArchivedPost.postStatus).toBe('COMPLETED')
      })
      await eventually(async () => {
        const {data} = await client.query({query: queries.post, variables: {postId}})
        expect(data.post.postId).toBe(postId)
        expect(data.post.adStatus).toBe('ACTIVE')
      })
    })
  })
})

describe('A new user', () => {
  let postId = uuidv4()
  let client, newClient

  beforeAll(async () => {
    // users, excluding the one that will be newly created
    await loginCache.clean()
    ;({client} = await loginCache.getCleanLogin())

    // client adds an ad post
    await client.mutate({
      mutation: mutations.addPost,
      variables: {postId, imageData, isAd: true, adPayment: 0.01},
    })
    await eventually(async () => {
      const {data} = await client.query({query: queries.post, variables: {postId}})
      expect(data.post.postId).toBe(postId)
      expect(data.post.postStatus).toBe('COMPLETED')
      expect(data.post.adStatus).toBe('PENDING')
    })

    // real user approves the ad post
    await realClient.mutate({mutation: mutations.approveAdPost, variables: {postId}})
    await eventually(async () => {
      const {data} = await client.query({query: queries.post, variables: {postId}})
      expect(data.post.postId).toBe(postId)
      expect(data.post.adStatus).toBe('ACTIVE')
    })
  })

  afterAll(async () => {
    if (newClient) await newClient.mutate({mutation: mutations.deleteUser})
  })

  test('Gets existing ads', async () => {
    ;({client: newClient} = await cognito.getAppSyncLogin())

    // newClient adds two posts so their feed has enough posts to support ads
    const [postId1, postId2] = [uuidv4(), uuidv4()]
    await newClient.mutate({mutation: mutations.addPost, variables: {postId: postId1, imageData}})
    await newClient.mutate({mutation: mutations.addPost, variables: {postId: postId2, imageData}})
    await eventually(async () => {
      const {data} = await newClient.query({query: queries.post, variables: {postId: postId1}})
      expect(data).toMatchObject({post: {postId: postId1, postStatus: 'COMPLETED'}})
    })
    await eventually(async () => {
      const {data} = await newClient.query({query: queries.post, variables: {postId: postId2}})
      expect(data).toMatchObject({post: {postId: postId2, postStatus: 'COMPLETED'}})
    })

    // newClient's feed should contain an ad
    await eventually(async () => {
      const {data} = await newClient.query({query: queries.selfFeed})
      expect(data.self.feed.items).toHaveLength(3)
      expect(data.self.feed.items[1].postId).toBe(postId)
    })
  })
})
