import fs from 'fs'
import {v4 as uuidv4} from 'uuid'

import {cognito, eventually, fixturePath, sleep} from '../../utils'
import {mutations, queries} from '../../schema'

const loginCache = new cognito.AppSyncLoginCache()
const grantData = fs.readFileSync(fixturePath('grant.jpg'))
const grantDataB64 = new Buffer.from(grantData).toString('base64')

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})
afterAll(async () => await loginCache.reset())

const cardTitle = 'Add a profile photo'

describe('New anonymous users do not get the add profile photo card', () => {
  let anonClient, anonUserId

  beforeAll(async () => {
    ;({client: anonClient, userId: anonUserId} = await cognito.getAnonymousAppSyncLogin())
  })

  afterAll(async () => {
    if (anonClient) await anonClient.mutate({mutation: mutations.deleteUser})
    anonClient = null
  })

  test('User is indeed anonymous', async () => {
    await eventually(async () => {
      const {data} = await anonClient.query({query: queries.self})
      expect(data.self.userId).toBe(anonUserId)
      expect(data.self.email).toBeNull()
      expect(data.self.userStatus).toBe('ANONYMOUS')
    })
  })

  test('The card does not appear', async () => {
    await sleep()
    await anonClient.query({query: queries.self}).then(({data}) => {
      expect(data.self.userId).toBe(anonUserId)
      expect(data.self.cards.items.filter((card) => card.title === cardTitle)).toHaveLength(0)
    })
  })
})

describe('New normal users and the add profile photo card', () => {
  let ourClient, ourUserId

  beforeAll(async () => {
    await loginCache.clean()
    ;({client: ourClient, userId: ourUserId} = await loginCache.getCleanLogin())
  })

  test('User is indeed normal', async () => {
    await eventually(async () => {
      const {data} = await ourClient.query({query: queries.self})
      expect(data.self.userId).toBe(ourUserId)
      expect(data.self.email).toBeDefined()
      expect(data.self.userStatus).toBe('ACTIVE')
      expect(data.self.photoPostId).toBeFalsy()
    })
  })

  test('The card appears by default and has correct format', async () => {
    await eventually(async () => {
      const {data} = await ourClient.query({query: queries.self})
      expect(data.self.cards.items.length).toBe(1)
      expect(data.self.cards.items[0].cardId).toBe(`${ourUserId}:ADD_PROFILE_PHOTO`)
      expect(data.self.cards.items[0].title).toBe(cardTitle)
      expect(data.self.cards.items[0].action).toBe(
        `https://real.app/apps/social/user/${ourUserId}/settings/photo`,
      )
    })
  })

  test('The card is automatically dismissed when the user adds a profile photo', async () => {
    // add a post they will use as a profile photo and verify that card is deleted
    const postId = uuidv4()
    await ourClient
      .mutate({mutation: mutations.addPost, variables: {postId, imageData: grantDataB64, takenInReal: true}})
      .then(({data: {addPost: post}}) => expect(post.postId).toBe(postId))

    await ourClient
      .mutate({mutation: mutations.setUserDetails, variables: {photoPostId: postId}})
      .then(({data: {setUserDetails: user}}) => expect(user.photo.url).toBeTruthy())

    await eventually(async () => {
      const {data} = await ourClient.query({query: queries.self})
      expect(data.self.userId).toBe(ourUserId)
      expect(data.self.cards.items.length).toBe(0)
    })
  })
})
