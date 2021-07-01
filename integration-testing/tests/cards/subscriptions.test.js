import {v4 as uuidv4} from 'uuid'

import {cognito, sleep} from '../../utils'
import {mutations, subscriptions} from '../../schema'

const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})
beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.reset())

test('Card message triggers cannot be called from external graphql client', async () => {
  const {client: ourClient, userId: ourUserId} = await loginCache.getCleanLogin()

  // verify we can't call the trigger method, even with well-formed input
  await ourClient
    .mutate({
      mutation: mutations.triggerCardNotification,
      variables: {
        input: {
          userId: ourUserId,
          type: 'ADDED',
          cardId: uuidv4(),
          title: 'title',
          action: 'https://real.app/apps/social/go',
        },
      },
      errorPolicy: 'all',
    })
    .then(({errors}) => {
      expect(errors).toHaveLength(1)
      expect(errors[0].message).toMatch(/ClientError: Access denied/)
    })
})

test('Cannot subscribe to other users notifications', async () => {
  const {client: ourClient} = await loginCache.getCleanLogin()
  const {client: theirClient, userId: theirUserId} = await loginCache.getCleanLogin()

  // we try to subscribe to their notifications, should never get called
  await ourClient
    .subscribe({query: subscriptions.onCardNotification, variables: {userId: theirUserId}})
    .subscribe({
      next: (response) => expect({cause: 'Subscription next() unexpectedly called', response}).toBeUndefined(),
      error: ({errors}) => {
        // AWS sometimes returns this error but usually it just silently ignores the invalid subscription
        const innerError = {
          errorType: 'ClientError',
          message: 'ClientError: Cannot subscribe to notifications intended for another user',
        }
        expect(errors).toMatchObject([{message: `Connection failed: ${JSON.stringify({errors: [innerError]})}`}])
      },
    })

  // they subscribe to their notifications
  const theirHandlers = []
  const theirSub = await theirClient
    .subscribe({query: subscriptions.onCardNotification, variables: {userId: theirUserId}})
    .subscribe({
      next: ({data: {onCardNotification: notification}}) => {
        const handler = theirHandlers.shift()
        expect(handler).toBeDefined()
        handler(notification)
      },
      error: (response) => expect({cause: 'Subscription error()', response}).toBeUndefined(),
    })
  const theirSubInitTimeout = sleep('subTimeout')
  await sleep('subInit')

  // they create a post
  const postId = uuidv4()
  await theirClient
    .mutate({
      mutation: mutations.addPost,
      variables: {postId, postType: 'TEXT_ONLY', text: 'lore ipsum'},
    })
    .then(({data}) => {
      expect(data.addPost.postId).toBe(postId)
      expect(data.addPost.postStatus).toBe('COMPLETED')
    })

  // we comment on their post (thus generating a card)
  let nextNotification = new Promise((resolve) => theirHandlers.push(resolve))
  await ourClient
    .mutate({mutation: mutations.addComment, variables: {commentId: uuidv4(), postId, text: 'lore!'}})
    .then(({data}) => expect(data.addComment.commentId).toBeTruthy())
  await nextNotification

  // we don't unsubscribe from our subscription because
  //  - it's not actually active, although I have yet to find a way to expect() that
  //  - unsubcribing results in the AWS SDK throwing errors
  // shut down the subscription
  theirSub.unsubscribe()
  await theirSubInitTimeout
})
