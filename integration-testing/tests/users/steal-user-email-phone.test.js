const gql = require('graphql-tag')
const {queries} = require('../../schema')
const cognito = require('../../utils/cognito')

const loginCache = new cognito.AppSyncLoginCache()
jest.retryTimes(1)

beforeAll(async () => {
  const ourPhone = '+15105551000'
  const theirPhone = '+15105551111'
  loginCache.addCleanLogin(await cognito.getAppSyncLogin(ourPhone))
  loginCache.addCleanLogin(await cognito.getAppSyncLogin(theirPhone))
})
beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.reset())
afterEach(async () => {})

const startChangeUserEmail = gql`
  mutation StartChangeUserEmail($email: AWSEmail!) {
    startChangeUserEmail(email: $email) {
      userId
      username
      email
      phoneNumber
    }
  }
`

const startChangeUserPhoneNumber = gql`
  mutation StartChangeUserPhoneNumber($phoneNumber: AWSPhone!) {
    startChangeUserPhoneNumber(phoneNumber: $phoneNumber) {
      userId
      username
      email
      phoneNumber
    }
  }
`

test('Enable, disable dating as a BASIC user, privacy', async () => {
  const {email: ourEmail, client: ourClient} = await loginCache.getCleanLogin()
  const {client: theirClient} = await loginCache.getCleanLogin()
  let ourPhoneNumber

  await ourClient.query({query: queries.self}).then(({data: {self: user}}) => {
    ourPhoneNumber = user.phoneNumber
  })

  await expect(
    theirClient.mutate({mutation: startChangeUserEmail, variables: {email: ourEmail}}),
  ).rejects.toThrow(/ClientError: User email is already used by other/)

  await expect(
    theirClient.mutate({mutation: startChangeUserPhoneNumber, variables: {phoneNumber: ourPhoneNumber}}),
  ).rejects.toThrow(/GraphQL error: ClientError: User phone is already used by other/)
})
