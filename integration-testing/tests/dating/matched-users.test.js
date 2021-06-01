import {v4 as uuidv4} from 'uuid'

import {cognito, eventually, generateRandomJpeg} from '../../utils'
import {mutations, queries} from '../../schema'

const imageData = generateRandomJpeg(8, 8)
const imageDataB64 = new Buffer.from(imageData).toString('base64')
const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})
beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.reset())

// generic dating criteria that matches itself
const datingVariables = {
  displayName: 'Hunter S',
  gender: 'FEMALE',
  location: {latitude: -30, longitude: -50}, // different from that used in other test suites
  height: 90,
  dateOfBirth: '2000-01-01',
  matchAgeRange: {min: 20, max: 30},
  matchGenders: ['FEMALE'],
  matchLocationRadius: 50,
  matchHeightRange: {min: 0, max: 110},
}

test('Ordering of potential matches', async () => {
  const {client: ourClient, userId: ourUserId} = await loginCache.getCleanLogin()
  const {client: other1Client, userId: other1UserId} = await loginCache.getCleanLogin()
  const {client: other2Client, userId: other2UserId} = await loginCache.getCleanLogin()
  const {client: other3Client, userId: other3UserId} = await loginCache.getCleanLogin()

  // everybody enables dating and matches each other
  const [pid1, pid2, pid3, pid4] = [uuidv4(), uuidv4(), uuidv4(), uuidv4()]
  await ourClient
    .mutate({mutation: mutations.addPost, variables: {postId: pid1, imageData: imageDataB64, takenInReal: true}})
    .then(({data: {addPost: post}}) => expect(post.postId).toBe(pid1))
  await ourClient
    .mutate({mutation: mutations.setUserDetails, variables: {...datingVariables, photoPostId: pid1}})
    .then(({data: {setUserDetails: user}}) => expect(user.userId).toBe(ourUserId))
  await other1Client
    .mutate({mutation: mutations.addPost, variables: {postId: pid2, imageData: imageDataB64, takenInReal: true}})
    .then(({data: {addPost: post}}) => expect(post.postId).toBe(pid2))
  await other1Client
    .mutate({mutation: mutations.setUserDetails, variables: {...datingVariables, photoPostId: pid2}})
    .then(({data: {setUserDetails: user}}) => expect(user.userId).toBe(other1UserId))
  await other2Client
    .mutate({mutation: mutations.addPost, variables: {postId: pid3, imageData: imageDataB64, takenInReal: true}})
    .then(({data: {addPost: post}}) => expect(post.postId).toBe(pid3))
  await other2Client
    .mutate({mutation: mutations.setUserDetails, variables: {...datingVariables, photoPostId: pid3}})
    .then(({data: {setUserDetails: user}}) => expect(user.userId).toBe(other2UserId))
  await other3Client
    .mutate({mutation: mutations.addPost, variables: {postId: pid4, imageData: imageDataB64, takenInReal: true}})
    .then(({data: {addPost: post}}) => expect(post.postId).toBe(pid4))
  await other3Client
    .mutate({mutation: mutations.setUserDetails, variables: {...datingVariables, photoPostId: pid4}})
    .then(({data: {setUserDetails: user}}) => expect(user.userId).toBe(other3UserId))
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
    const {data, errors} = await other1Client.mutate({
      mutation: mutations.setUserDatingStatus,
      variables: {status: 'ENABLED'},
      errorPolicy: 'all',
    })
    expect(errors).toBeUndefined()
    expect(data.setUserDatingStatus.datingStatus).toBe('ENABLED')
  })
  await eventually(async () => {
    const {data, errors} = await other2Client.mutate({
      mutation: mutations.setUserDatingStatus,
      variables: {status: 'ENABLED'},
      errorPolicy: 'all',
    })
    expect(errors).toBeUndefined()
    expect(data.setUserDatingStatus.datingStatus).toBe('ENABLED')
  })
  await eventually(async () => {
    const {data, errors} = await other3Client.mutate({
      mutation: mutations.setUserDatingStatus,
      variables: {status: 'ENABLED'},
      errorPolicy: 'all',
    })
    expect(errors).toBeUndefined()
    expect(data.setUserDatingStatus.datingStatus).toBe('ENABLED')
  })

  // check list of potential matches, order not defined
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.matchedUsers, variables: {matchStatus: 'POTENTIAL'}})
    const matchedUserIds = data.self.matchedUsers.items.map((i) => i.userId)
    expect(matchedUserIds.sort()).toEqual([other1UserId, other2UserId, other3UserId].sort())
  })

  // other2 earns an approval, check that moves them to the front
  await other3Client.mutate({mutation: mutations.approveMatch, variables: {userId: other2UserId}})
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.matchedUsers, variables: {matchStatus: 'POTENTIAL'}})
    const [firstUserId, ...otherUserIds] = data.self.matchedUsers.items.map((i) => i.userId)
    expect(firstUserId).toBe(other2UserId)
    expect(otherUserIds.sort()).toEqual([other1UserId, other3UserId].sort())
  })

  // other3 earns an approval, check that ties them with other2
  await other1Client.mutate({mutation: mutations.approveMatch, variables: {userId: other3UserId}})
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.matchedUsers, variables: {matchStatus: 'POTENTIAL'}})
    const [lastUserId, ...firstUserIds] = data.self.matchedUsers.items.map((i) => i.userId).reverse()
    expect(lastUserId).toBe(other1UserId)
    expect(firstUserIds.sort()).toEqual([other2UserId, other3UserId].sort())
  })

  // other3 earns another approval, check now they are alone in the front
  await other2Client.mutate({mutation: mutations.approveMatch, variables: {userId: other3UserId}})
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.matchedUsers, variables: {matchStatus: 'POTENTIAL'}})
    const matchedUserIds = data.self.matchedUsers.items.map((i) => i.userId)
    expect(matchedUserIds).toEqual([other3UserId, other2UserId, other1UserId])
  })
})

test('Privacy, lifecycle to REJECT', async () => {
  const {client: ourClient, userId: ourUserId} = await loginCache.getCleanLogin()
  const {client: other1Client, userId: other1UserId} = await loginCache.getCleanLogin()

  // everybody enables dating and matches each other
  const [pid1, pid2] = [uuidv4(), uuidv4(), uuidv4(), uuidv4()]
  await ourClient
    .mutate({mutation: mutations.addPost, variables: {postId: pid1, imageData: imageDataB64, takenInReal: true}})
    .then(({data: {addPost: post}}) => expect(post.postId).toBe(pid1))
  await ourClient
    .mutate({mutation: mutations.setUserDetails, variables: {...datingVariables, photoPostId: pid1}})
    .then(({data: {setUserDetails: user}}) => expect(user.userId).toBe(ourUserId))
  await other1Client
    .mutate({mutation: mutations.addPost, variables: {postId: pid2, imageData: imageDataB64, takenInReal: true}})
    .then(({data: {addPost: post}}) => expect(post.postId).toBe(pid2))
  await other1Client
    .mutate({mutation: mutations.setUserDetails, variables: {...datingVariables, photoPostId: pid2}})
    .then(({data: {setUserDetails: user}}) => expect(user.userId).toBe(other1UserId))
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
    const {data, errors} = await other1Client.mutate({
      mutation: mutations.setUserDatingStatus,
      variables: {status: 'ENABLED'},
      errorPolicy: 'all',
    })
    expect(errors).toBeUndefined()
    expect(data.setUserDatingStatus.datingStatus).toBe('ENABLED')
  })

  // check all our our lists of matches
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.allMatchedUsersForUser, variables: {userId: ourUserId}})
    expect(data.user.potentialMatchedUsers.items.map((i) => i.userId)).toEqual([other1UserId])
    expect(data.user.rejectedMatchedUsers.items).toEqual([])
    expect(data.user.approvedMatchedUsers.items).toEqual([])
    expect(data.user.confirmedMatchedUsers.items).toEqual([])
  })

  // verify they can't see our lists of matches
  await other1Client
    .query({query: queries.allMatchedUsersForUser, variables: {userId: ourUserId}})
    .then(({data: {user}}) => {
      expect(user.potentialMatchedUsers).toBeNull()
      expect(user.rejectedMatchedUsers).toBeNull()
      expect(user.approvedMatchedUsers).toBeNull()
      expect(user.confirmedMatchedUsers).toBeNull()
    })

  // we reject them, check lists of matches
  await ourClient.mutate({mutation: mutations.rejectMatch, variables: {userId: other1UserId}})
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.allMatchedUsersForUser, variables: {userId: ourUserId}})
    expect(data.user.potentialMatchedUsers.items).toEqual([])
    expect(data.user.rejectedMatchedUsers.items.map((i) => i.userId)).toEqual([other1UserId])
    expect(data.user.approvedMatchedUsers.items).toEqual([])
    expect(data.user.confirmedMatchedUsers.items).toEqual([])
  })

  // verify we can't query for NOT_MATCHED
  await expect(
    ourClient.query({query: queries.matchedUsers, variables: {matchStatus: 'NOT_MATCHED'}}),
  ).rejects.toThrow(/ClientError: Cannot request using status NOT_MATCHED/)
})

test('Lifecycle to CONFIRMED', async () => {
  const {client: ourClient, userId: ourUserId} = await loginCache.getCleanLogin()
  const {client: other1Client, userId: other1UserId} = await loginCache.getCleanLogin()

  // everybody enables dating and matches each other
  const [pid1, pid2] = [uuidv4(), uuidv4(), uuidv4(), uuidv4()]
  await ourClient
    .mutate({mutation: mutations.addPost, variables: {postId: pid1, imageData: imageDataB64, takenInReal: true}})
    .then(({data: {addPost: post}}) => expect(post.postId).toBe(pid1))
  await ourClient
    .mutate({mutation: mutations.setUserDetails, variables: {...datingVariables, photoPostId: pid1}})
    .then(({data: {setUserDetails: user}}) => expect(user.userId).toBe(ourUserId))
  await other1Client
    .mutate({mutation: mutations.addPost, variables: {postId: pid2, imageData: imageDataB64, takenInReal: true}})
    .then(({data: {addPost: post}}) => expect(post.postId).toBe(pid2))
  await other1Client
    .mutate({mutation: mutations.setUserDetails, variables: {...datingVariables, photoPostId: pid2}})
    .then(({data: {setUserDetails: user}}) => expect(user.userId).toBe(other1UserId))
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
    const {data, errors} = await other1Client.mutate({
      mutation: mutations.setUserDatingStatus,
      variables: {status: 'ENABLED'},
      errorPolicy: 'all',
    })
    expect(errors).toBeUndefined()
    expect(data.setUserDatingStatus.datingStatus).toBe('ENABLED')
  })

  // check all our our lists of matches
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.allMatchedUsersForUser, variables: {userId: ourUserId}})
    expect(data.user.potentialMatchedUsers.items.map((i) => i.userId)).toEqual([other1UserId])
    expect(data.user.rejectedMatchedUsers.items).toEqual([])
    expect(data.user.approvedMatchedUsers.items).toEqual([])
    expect(data.user.confirmedMatchedUsers.items).toEqual([])
  })

  // we approve them, check lists of matches
  await ourClient.mutate({mutation: mutations.approveMatch, variables: {userId: other1UserId}})
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.allMatchedUsersForUser, variables: {userId: ourUserId}})
    expect(data.user.potentialMatchedUsers.items).toEqual([])
    expect(data.user.rejectedMatchedUsers.items).toEqual([])
    expect(data.user.approvedMatchedUsers.items.map((i) => i.userId)).toEqual([other1UserId])
    expect(data.user.confirmedMatchedUsers.items).toEqual([])
  })

  // they approve us, check lists of matches
  await other1Client.mutate({mutation: mutations.approveMatch, variables: {userId: ourUserId}})
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.allMatchedUsersForUser, variables: {userId: ourUserId}})
    expect(data.user.potentialMatchedUsers.items).toEqual([])
    expect(data.user.rejectedMatchedUsers.items).toEqual([])
    expect(data.user.approvedMatchedUsers.items).toEqual([])
    expect(data.user.confirmedMatchedUsers.items.map((i) => i.userId)).toEqual([other1UserId])
  })
})
