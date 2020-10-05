const moment = require('moment')
const cognito = require('../utils/cognito')
const misc = require('../utils/misc')
const {queries, mutations} = require('../schema')
const uuidv4 = require('uuid/v4')

const loginCache = new cognito.AppSyncLoginCache()
jest.retryTimes(1)

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})
beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.reset())

test('Find contacts by email & phoneNumber too many', async () => {
  const {client, email} = await loginCache.getCleanLogin()
  const contacts = Array(101).fill({contactId: 'contactId', emails: [email]})
  await misc.sleep(2000)
  await expect(client.query({query: queries.findContacts, variables: {contacts}})).rejects.toThrow(
    /Cannot submit more than 100 contact inputs/,
  )
})

test('Find contacts can handle duplicate emails', async () => {
  const {client, userId, email, username} = await loginCache.getCleanLogin()
  await misc.sleep(2000)
  const contacts = [{contactId: 'contactId', emails: [email, email]}]
  await client.query({query: queries.findContacts, variables: {contacts}}).then(({data: {findContacts}}) => {
    expect(findContacts).toHaveLength(1)
    expect(findContacts[0].contactId).toBe('contactId')
    expect(findContacts[0].user.userId).toBe(userId)
    expect(findContacts[0].user.username).toBe(username)
  })
})

test('Find users by email', async () => {
  const {
    client: ourClient,
    userId: ourUserId,
    email: ourEmail,
    username: ourUsername,
  } = await loginCache.getCleanLogin()
  const {userId: other1UserId, email: other1Email, username: other1Username} = await loginCache.getCleanLogin()
  const {userId: other2UserId, email: other2Email, username: other2Username} = await loginCache.getCleanLogin()
  const cmp = (a, b) => a.user.userId.localeCompare(b.user.userId)

  // how each user will appear in search results, based on our query
  const us = {
    __typename: 'FoundContact',
    contactId: 'contactId_1',
    user: {__typename: 'User', userId: ourUserId, username: ourUsername},
  }
  const other1 = {
    __typename: 'FoundContact',
    contactId: 'contactId_2',
    user: {__typename: 'User', userId: other1UserId, username: other1Username},
  }
  const other2 = {
    __typename: 'FoundContact',
    contactId: 'contactId_3',
    user: {__typename: 'User', userId: other2UserId, username: other2Username},
  }

  // find no users
  await misc.sleep(2000)
  let contacts = [{contactId: 'contactId_1', emails: ['x' + ourEmail]}]
  await ourClient
    .query({query: queries.findContacts, variables: {contacts}})
    .then(({data: {findContacts}}) => expect(findContacts).toEqual([]))

  // find one user
  contacts = [{contactId: 'contactId_2', emails: [other1Email]}]
  await ourClient.query({query: queries.findContacts, variables: {contacts}}).then(({data: {findContacts}}) => {
    expect(findContacts).toHaveLength(1)
    expect(findContacts[0]).toStrictEqual(other1)
  })

  contacts = [{contactId: 'contactId_1', emails: [ourEmail, 'AA' + other1Email]}]
  await ourClient.query({query: queries.findContacts, variables: {contacts}}).then(({data: {findContacts}}) => {
    expect(findContacts).toHaveLength(1)
    expect(findContacts[0]).toStrictEqual(us)
  })

  // find multiple users
  contacts = [
    {
      contactId: 'contactId_1',
      emails: [ourEmail],
    },
    {
      contactId: 'contactId_2',
      emails: [other1Email],
    },
    {
      contactId: 'contactId_3',
      emails: [other2Email],
    },
  ]

  await ourClient.query({query: queries.findContacts, variables: {contacts}}).then(({data: {findContacts}}) => {
    expect(findContacts.length).toBe(3)
    expect(findContacts.sort(cmp)).toStrictEqual([us, other1, other2].sort(cmp))
  })
})

describe('wrapper to ensure cleanup', () => {
  const theirPhone = '+15105551011'
  let theirClient, theirUserId, theirUsername, theirEmail
  beforeAll(async () => {
    ;({
      client: theirClient,
      userId: theirUserId,
      email: theirEmail,
      username: theirUsername,
    } = await cognito.getAppSyncLogin(theirPhone))
  })
  afterAll(async () => {
    if (theirClient) await theirClient.mutate({mutation: mutations.deleteUser})
  })

  test('Find users by phone, and by phone and email', async () => {
    const {
      client: ourClient,
      userId: ourUserId,
      email: ourEmail,
      username: ourUsername,
    } = await loginCache.getCleanLogin()
    const cmp = (a, b) => a.user.userId.localeCompare(b.user.userId)

    // how each user will appear in search results, based on our query
    const us = {
      __typename: 'FoundContact',
      contactId: 'contactId_1',
      user: {__typename: 'User', userId: ourUserId, username: ourUsername},
    }
    const them = {
      __typename: 'FoundContact',
      contactId: 'contactId_2',
      user: {__typename: 'User', userId: theirUserId, username: theirUsername},
    }

    // find them by just phone
    await misc.sleep(2000)
    let contacts = [{contactId: 'contactId_2', phones: [theirPhone]}]
    await ourClient.query({query: queries.findContacts, variables: {contacts}}).then(({data: {findContacts}}) => {
      expect(findContacts.length).toBe(1)
      expect(findContacts[0]).toStrictEqual(them)
    })

    // find us and them by phone and email, make sure they don't duplicate
    contacts = [
      {
        contactId: 'contactId_1',
        emails: [ourEmail],
      },
      {
        contactId: 'contactId_2',
        emails: [theirEmail],
        phones: [theirPhone],
      },
    ]
    await ourClient.query({query: queries.findContacts, variables: {contacts}}).then(({data: {findContacts}}) => {
      expect(findContacts.length).toBe(2)
      expect(findContacts.sort(cmp)).toEqual([us, them].sort(cmp))
    })
  })
})

test('Find contacts sends cards to the users that were found', async () => {
  const {
    client: ourClient,
    userId: ourUserId,
    email: ourEmail,
    username: ourUsername,
  } = await loginCache.getCleanLogin()
  const {client: otherClient, userId: otherUserId, email: otherEmail} = await loginCache.getCleanLogin()
  const {
    client: other1Client,
    userId: other1UserId,
    email: other1Email,
    username: other1Username,
  } = await loginCache.getCleanLogin()
  const {client: other2Client, userId: other2UserId, email: other2Email} = await loginCache.getCleanLogin()
  const randomEmail = `${uuidv4()}@real.app`
  const other1 = {
    __typename: 'FoundContact',
    contactId: 'contactId_1',
    user: {__typename: 'User', userId: other1UserId, username: other1Username},
  }

  // find One User
  let contacts = [{contactId: 'contactId_1', emails: [other1Email, randomEmail]}]
  await ourClient
    .query({query: queries.findContacts, variables: {contacts}})
    .then(({data: {findContacts}}) => expect(findContacts[0]).toStrictEqual(other1))

  // check called user has card
  await misc.sleep(2000)
  const cardId = await other1Client.query({query: queries.self}).then(({data: {self}}) => {
    expect(self.userId).toBe(other1UserId)
    const card = self.cards.items[0]
    expect(card.cardId).toBe(`${other1UserId}:CONTACT_JOINED:${ourUserId}`)
    expect(card.title).toBe(`${ourUsername} joined REAL`)
    expect(card.subTitle).toBeNull()
    expect(card.action).toBe(`https://real.app/user/${ourUserId}`)
    return card.cardId
  })

  // dismiss the card
  await other1Client
    .mutate({mutation: mutations.deleteCard, variables: {cardId}})
    .then(({data}) => expect(data.deleteCard.cardId).toBe(cardId))

  // find different Users with new user
  contacts = [
    {
      contactId: 'contactId_1',
      emails: [ourEmail],
    },
    {
      contactId: 'contactId_2',
      emails: [other1Email],
    },
    {
      contactId: 'contactId_3',
      emails: [other2Email],
    },
  ]
  await ourClient.query({query: queries.findContacts, variables: {contacts}}).then(({data: {findContacts}}) => {
    expect(findContacts.length).toBe(3)
    expect(findContacts.map((item) => item.user.userId).sort()).toEqual(
      [ourUserId, other1UserId, other2UserId].sort(),
    )
  })
  // check first called user has card
  await misc.sleep(2000)
  await other1Client.query({query: queries.self}).then(({data: {self}}) => {
    expect(self.userId).toBe(other1UserId)
    expect(self.cards.items[0].cardId).toBe(`${other1UserId}:CONTACT_JOINED:${ourUserId}`)
  })
  // check second called user has card
  await other2Client.query({query: queries.self}).then(({data: {self}}) => {
    expect(self.userId).toBe(other2UserId)
    expect(self.cards.items[0].cardId).toBe(`${other2UserId}:CONTACT_JOINED:${ourUserId}`)
  })

  // find different Users with other new user
  contacts = [
    {
      contactId: 'contactId_4',
      emails: [otherEmail],
    },
    {
      contactId: 'contactId_2',
      emails: [other1Email],
    },
    {
      contactId: 'contactId_3',
      emails: [other2Email],
    },
  ]
  await otherClient.query({query: queries.findContacts, variables: {contacts}}).then(({data: {findContacts}}) => {
    expect(findContacts.map((item) => item.user.userId).sort()).toEqual(
      [otherUserId, other1UserId, other2UserId].sort(),
    )
  })
  // check first called user has card
  await misc.sleep(2000)
  await other1Client.query({query: queries.self}).then(({data: {self}}) => {
    expect(self.userId).toBe(other1UserId)
    expect(self.cards.items[0].cardId).toBe(`${other1UserId}:CONTACT_JOINED:${otherUserId}`)
  })
  // check second called user has card
  await other2Client.query({query: queries.self}).then(({data: {self}}) => {
    expect(self.userId).toBe(other2UserId)
    expect(self.cards.items[0].cardId).toBe(`${other2UserId}:CONTACT_JOINED:${otherUserId}`)
  })
})

test('Find contacts and check lastFoundContactsAt', async () => {
  const {client: ourClient, userId: ourUserId, email: ourEmail} = await loginCache.getCleanLogin()
  const {client: theirClient} = await loginCache.getCleanLogin()

  // Check initialize of lastFoundContactsAt
  await ourClient.query({query: queries.self}).then(({data: {self}}) => {
    expect(self.lastFoundContactsAt).toBeNull()
  })

  // Run the findContacts Query
  let before = moment().toISOString()
  const contacts = [{contactId: 'contactId_1', emails: [ourEmail]}]
  await ourClient
    .query({query: queries.findContacts, variables: {contacts}})
    .then(({data: {findContacts}}) => expect(findContacts.map((i) => i.user.userId)).toEqual([ourUserId]))
  let after = moment().toISOString()

  // Then check lastFoundContactsAt timestamp
  await misc.sleep(2000)
  await ourClient.query({query: queries.self}).then(({data: {self}}) => {
    expect(before <= self.lastFoundContactsAt).toBe(true)
    expect(after >= self.lastFoundContactsAt).toBe(true)
  })

  // Check another user can't see lastFoundContactsAt
  await theirClient.query({query: queries.user, variables: {userId: ourUserId}}).then(({data: {user}}) => {
    expect(user.userId).toBe(ourUserId)
    expect(user.lastFoundContactsAt).toBeNull()
  })

  // Call findContacts again and check the lastFoundContactsAt is updated correctly
  await ourClient
    .query({query: queries.findContacts, variables: {contacts}})
    .then(({data: {findContacts}}) => expect(findContacts.map((i) => i.user.userId)).toEqual([ourUserId]))
  await misc.sleep(2000)

  await ourClient.query({query: queries.self}).then(({data: {self}}) => {
    expect(after <= self.lastFoundContactsAt).toBe(true)
  })
})
