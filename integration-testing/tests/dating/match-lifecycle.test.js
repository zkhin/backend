import {v4 as uuidv4} from 'uuid'

import {cognito, eventually, generateRandomJpeg} from '../../utils'
import {mutations, queries} from '../../schema'

const imageData = generateRandomJpeg(8, 8)
const imageDataB64 = new Buffer.from(imageData).toString('base64')
const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})
beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.reset())

// generic dating criteria that matches itself
const datingVariables = {
  displayName: 'Hunter S',
  gender: 'FEMALE',
  location: {latitude: 30, longitude: 50}, // different from that used in other test suites
  dateOfBirth: '2000-01-01',
  height: 90,
  matchAgeRange: {min: 20, max: 30},
  matchGenders: ['FEMALE'],
  matchLocationRadius: 50,
  matchHeightRange: {min: 0, max: 110},
}

test('Reject and approve match - error cases and basic success', async () => {
  const {client: ourClient, userId: ourUserId} = await loginCache.getCleanLogin()
  const {client: theirClient, userId: theirUserId} = await loginCache.getCleanLogin()

  // verify we can't approve or reject them
  await expect(
    ourClient.mutate({mutation: mutations.rejectMatch, variables: {userId: theirUserId}}),
  ).rejects.toThrow(/ClientError: Match does not exist/)
  await expect(
    ourClient.mutate({mutation: mutations.approveMatch, variables: {userId: theirUserId}}),
  ).rejects.toThrow(/ClientError: Match does not exist/)

  // we both set details that would *almost* make us match each other, and enable dating
  const [pid1, pid2] = [uuidv4(), uuidv4()]
  await ourClient
    .mutate({mutation: mutations.addPost, variables: {postId: pid1, imageData: imageDataB64, takenInReal: true}})
    .then(({data: {addPost: post}}) => expect(post.postId).toBe(pid1))
  await ourClient
    .mutate({
      mutation: mutations.setUserDetails,
      variables: {...datingVariables, gender: 'MALE', photoPostId: pid1},
    })
    .then(({data: {setUserDetails: user}}) => expect(user.userId).toBe(ourUserId))
  await theirClient
    .mutate({mutation: mutations.addPost, variables: {postId: pid2, imageData: imageDataB64, takenInReal: true}})
    .then(({data: {addPost: post}}) => expect(post.postId).toBe(pid2))
  await theirClient
    .mutate({mutation: mutations.setUserDetails, variables: {...datingVariables, photoPostId: pid2}})
    .then(({data: {setUserDetails: user}}) => expect(user.userId).toBe(theirUserId))
  await eventually(async () => {
    const {data, errors} = await ourClient.mutate({
      mutation: mutations.setUserDatingStatus,
      variables: {status: 'ENABLED'},
      errorPolicy: 'all',
    })
    expect(errors).toBeUndefined()
    expect(data.setUserDatingStatus.datingStatus).toBe('ENABLED')
  })
  await eventually(async () => {
    const {data, errors} = await theirClient.mutate({
      mutation: mutations.setUserDatingStatus,
      variables: {status: 'ENABLED'},
      errorPolicy: 'all',
    })
    expect(errors).toBeUndefined()
    expect(data.setUserDatingStatus.datingStatus).toBe('ENABLED')
  })

  // verify we still can't approve or reject them
  await expect(
    ourClient.mutate({mutation: mutations.rejectMatch, variables: {userId: theirUserId}}),
  ).rejects.toThrow(/ClientError: Match does not exist/)
  await expect(
    ourClient.mutate({mutation: mutations.approveMatch, variables: {userId: theirUserId}}),
  ).rejects.toThrow(/ClientError: Match does not exist/)

  // we adjust our details, so now we are a match, so now we can reject them and they can approve us
  await ourClient.mutate({mutation: mutations.setUserDetails, variables: {gender: 'FEMALE'}})
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.user, variables: {userId: theirUserId}})
    expect(data.user.matchStatus).toBe('POTENTIAL')
  })
  await ourClient.mutate({mutation: mutations.rejectMatch, variables: {userId: theirUserId}})
  await theirClient.mutate({mutation: mutations.approveMatch, variables: {userId: ourUserId}})
})

test('POTENTIAL -> CONFIRMED', async () => {
  const {client: ourClient, userId: ourUserId} = await loginCache.getCleanLogin()
  const {client: theirClient, userId: theirUserId} = await loginCache.getCleanLogin()

  // we both set details that would make us match each other, and enable dating
  const [pid1, pid2] = [uuidv4(), uuidv4()]
  await ourClient
    .mutate({mutation: mutations.addPost, variables: {postId: pid1, imageData: imageDataB64, takenInReal: true}})
    .then(({data: {addPost: post}}) => expect(post.postId).toBe(pid1))
  await ourClient
    .mutate({mutation: mutations.setUserDetails, variables: {...datingVariables, photoPostId: pid1}})
    .then(({data: {setUserDetails: user}}) => expect(user.userId).toBe(ourUserId))
  await theirClient
    .mutate({mutation: mutations.addPost, variables: {postId: pid2, imageData: imageDataB64, takenInReal: true}})
    .then(({data: {addPost: post}}) => expect(post.postId).toBe(pid2))
  await theirClient
    .mutate({mutation: mutations.setUserDetails, variables: {...datingVariables, photoPostId: pid2}})
    .then(({data: {setUserDetails: user}}) => expect(user.userId).toBe(theirUserId))
  await eventually(async () => {
    const {data, errors} = await ourClient.mutate({
      mutation: mutations.setUserDatingStatus,
      variables: {status: 'ENABLED'},
      errorPolicy: 'all',
    })
    expect(errors).toBeUndefined()
    expect(data.setUserDatingStatus.datingStatus).toBe('ENABLED')
  })
  await eventually(async () => {
    const {data, errors} = await theirClient.mutate({
      mutation: mutations.setUserDatingStatus,
      variables: {status: 'ENABLED'},
      errorPolicy: 'all',
    })
    expect(errors).toBeUndefined()
    expect(data.setUserDatingStatus.datingStatus).toBe('ENABLED')
  })
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.user, variables: {userId: theirUserId}})
    expect(data.user.matchStatus).toBe('POTENTIAL')
  })
  await eventually(async () => {
    const {data} = await theirClient.query({query: queries.user, variables: {userId: ourUserId}})
    expect(data.user.matchStatus).toBe('POTENTIAL')
  })

  // we approve them, check statues
  await ourClient.mutate({mutation: mutations.approveMatch, variables: {userId: theirUserId}})
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.user, variables: {userId: theirUserId}})
    expect(data.user.matchStatus).toBe('APPROVED')
  })
  await eventually(async () => {
    const {data} = await theirClient.query({query: queries.user, variables: {userId: ourUserId}})
    expect(data.user.matchStatus).toBe('POTENTIAL')
  })

  // check now we can't reject them, or re-approve them
  await expect(
    ourClient.mutate({mutation: mutations.rejectMatch, variables: {userId: theirUserId}}),
  ).rejects.toThrow(/ClientError: Invalid match transition/)
  await expect(
    ourClient.mutate({mutation: mutations.approveMatch, variables: {userId: theirUserId}}),
  ).rejects.toThrow(/ClientError: Invalid match transition/)

  // they approve us, check statuses
  await theirClient.mutate({mutation: mutations.approveMatch, variables: {userId: ourUserId}})
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.user, variables: {userId: theirUserId}})
    expect(data.user.matchStatus).toBe('CONFIRMED')
  })
  await eventually(async () => {
    const {data} = await theirClient.query({query: queries.user, variables: {userId: ourUserId}})
    expect(data.user.matchStatus).toBe('CONFIRMED')
  })

  // check if the group chat is created with our and their
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.self})
    expect(data.self.userId).toBe(ourUserId)
    expect(data.self.cardCount).toBeGreaterThanOrEqual(1)
    expect(data.self.chatCount).toBe(1)
    expect(data.self.chatsWithUnviewedMessagesCount).toBe(1)
    // Unread chat message card
    const card = data.self.cards.items[0]
    expect(card.title).toBe('You have 1 chat with new messages')
    expect(card.action).toBe('https://real.app/chat/')
    const secondCard = data.self.cards.items[1]
    expect(secondCard.title).toBe("It's a match! Kick things off by saying hello!")
    expect(secondCard.action).toBe(`https://real.app/user/${ourUserId}/dating_matched`)
    const chat = data.self.chats.items[0]
    expect(chat.chatType).toBe('GROUP')
    expect(chat.messagesCount).toBe(4)
    expect(chat.usersCount).toBe(2)
    expect(chat.users.items.map((u) => u.userId).sort()).toEqual([ourUserId, theirUserId].sort())
  })

  // check now they can't reject us, or re-approve us
  await expect(
    theirClient.mutate({mutation: mutations.rejectMatch, variables: {userId: ourUserId}}),
  ).rejects.toThrow(/ClientError: Invalid match transition/)
  await expect(
    theirClient.mutate({mutation: mutations.approveMatch, variables: {userId: ourUserId}}),
  ).rejects.toThrow(/ClientError: Invalid match transition/)
})

test('POTENTIAL -> REJECTED & APPROVED', async () => {
  const {client: ourClient, userId: ourUserId} = await loginCache.getCleanLogin()
  const {client: theirClient, userId: theirUserId} = await loginCache.getCleanLogin()

  // we both set details that would make us match each other, and enable dating
  const [pid1, pid2] = [uuidv4(), uuidv4()]
  await ourClient
    .mutate({mutation: mutations.addPost, variables: {postId: pid1, imageData: imageDataB64, takenInReal: true}})
    .then(({data: {addPost: post}}) => expect(post.postId).toBe(pid1))
  await ourClient.mutate({
    mutation: mutations.setUserDetails,
    variables: {...datingVariables, photoPostId: pid1},
  })
  await theirClient
    .mutate({mutation: mutations.addPost, variables: {postId: pid2, imageData: imageDataB64, takenInReal: true}})
    .then(({data: {addPost: post}}) => expect(post.postId).toBe(pid2))
  await theirClient.mutate({
    mutation: mutations.setUserDetails,
    variables: {...datingVariables, photoPostId: pid2},
  })
  await eventually(async () => {
    const {data, errors} = await ourClient.mutate({
      mutation: mutations.setUserDatingStatus,
      variables: {status: 'ENABLED'},
      errorPolicy: 'all',
    })
    expect(errors).toBeUndefined()
    expect(data.setUserDatingStatus.datingStatus).toBe('ENABLED')
  })
  await eventually(async () => {
    const {data, errors} = await theirClient.mutate({
      mutation: mutations.setUserDatingStatus,
      variables: {status: 'ENABLED'},
      errorPolicy: 'all',
    })
    expect(errors).toBeUndefined()
    expect(data.setUserDatingStatus.datingStatus).toBe('ENABLED')
  })
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.user, variables: {userId: theirUserId}})
    expect(data.user.matchStatus).toBe('POTENTIAL')
  })
  await eventually(async () => {
    const {data} = await theirClient.query({query: queries.user, variables: {userId: ourUserId}})
    expect(data.user.matchStatus).toBe('POTENTIAL')
  })

  // we reject them, check statues
  await ourClient.mutate({mutation: mutations.rejectMatch, variables: {userId: theirUserId}})
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.user, variables: {userId: theirUserId}})
    expect(data.user.matchStatus).toBe('REJECTED')
  })
  await eventually(async () => {
    const {data} = await theirClient.query({query: queries.user, variables: {userId: ourUserId}})
    expect(data.user.matchStatus).toBe('POTENTIAL')
  })

  // check now we can't reject them, or re-approve them
  await expect(
    ourClient.mutate({mutation: mutations.rejectMatch, variables: {userId: theirUserId}}),
  ).rejects.toThrow(/ClientError: Invalid match transition/)
  await expect(
    ourClient.mutate({mutation: mutations.approveMatch, variables: {userId: theirUserId}}),
  ).rejects.toThrow(/ClientError: Invalid match transition/)

  // they approve us, check statuses
  await theirClient.mutate({mutation: mutations.approveMatch, variables: {userId: ourUserId}})
  await eventually(async () => {
    const {data} = await theirClient.query({query: queries.user, variables: {userId: ourUserId}})
    expect(data.user.matchStatus).toBe('APPROVED')
  })
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.user, variables: {userId: theirUserId}})
    expect(data.user.matchStatus).toBe('REJECTED')
  })

  // check now they can't reject us, or re-approve us
  await expect(
    theirClient.mutate({mutation: mutations.rejectMatch, variables: {userId: ourUserId}}),
  ).rejects.toThrow(/ClientError: Invalid match transition/)
  await expect(
    theirClient.mutate({mutation: mutations.approveMatch, variables: {userId: ourUserId}}),
  ).rejects.toThrow(/ClientError: Invalid match transition/)
})
