const fs = require('fs')
const path = require('path')
const {v4: uuidv4} = require('uuid')

const {cognito, eventually, sleep} = require('../../utils')
const {mutations, queries} = require('../../schema')

const loginCache = new cognito.AppSyncLoginCache()
const grantData = fs.readFileSync(path.join(__dirname, '..', '..', 'fixtures', 'grant.jpg'))
const grantDataB64 = new Buffer.from(grantData).toString('base64')

let anonClient, anonUserId
beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})
beforeEach(async () => await loginCache.clean())
afterAll(async () => {
  if (anonClient) await anonClient.mutate({mutation: mutations.deleteUser})
  anonClient = null
})

const cardTitle = 'Add a profile photo'

describe('New anonymous users do not get the add profile photo card', () => {
  beforeAll(async () => {
    ;({client: anonClient, userId: anonUserId} = await cognito.getAnonymousAppSyncLogin())
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
      expect(data.self.cards.items[0].action).toBe(`https://real.app/user/${ourUserId}/settings/photo`)
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
