/* Helper utils to initialize and destroy the 'real' user.
 *
 * Any test that utilizes the real user should:
 *   - use these utility functions, not build the 'real' user itself
 *   - not be run in parrallel with other tests
 *
 * Note that simply changing another user's username to 'real' doesn't
 * work consistently due to server-side caching of the real user.
 */

import {getAppSyncLogin} from './cognito'
import {sleep} from './timing'
import {mutations} from '../schema'

let realLogin = null

export const getLogin = async () => {
  if (!realLogin) {
    realLogin = await getAppSyncLogin()
    realLogin.username = 'real'
  }
  await realLogin.client.mutate({mutation: mutations.setUsername, variables: {username: realLogin.username}})
  await sleep('gsi')
  return realLogin
}

export const cleanLogin = async () => {
  if (realLogin)
    await realLogin.client.mutate({mutation: mutations.resetUser, variables: {newUsername: realLogin.username}})
}

export const resetLogin = async () => {
  if (realLogin) await realLogin.client.mutate({mutation: mutations.resetUser})
  realLogin = null
}
