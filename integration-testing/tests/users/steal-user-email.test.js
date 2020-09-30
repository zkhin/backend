const gql = require('graphql-tag')

const cognito = require('../../utils/cognito')

const loginCache = new cognito.AppSyncLoginCache()
jest.retryTimes(1)

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
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

test('Enable, disable dating as a BASIC user, privacy', async () => {
  const {email: ourEmail} = await loginCache.getCleanLogin()
  const {client: theirClient} = await loginCache.getCleanLogin()

  await expect(
    theirClient.mutate({mutation: startChangeUserEmail, variables: {email: ourEmail}}),
  ).rejects.toThrow(/ClientError: User email is already used by other/)
})
