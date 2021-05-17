/* Sleep for the specified time.
 *
 * Accepts:
 *  - the number of seconds to sleep for, as a float
 *  - several 'reason' keywords which map to various lengths of sleep
 *  - defaults to 5 seconds if no keyword supplied
 *
 * Also accepts various keywords, which is the preferred way to call
 * to avoid having random constants defined throughout the code */
const sleep = (input) => {
  const sec = (() => {
    if (typeof input === 'number') return input
    if (input === 'gsi') return 1
    if (input === 'long') return 10
    if (input === 'subInit') return 2
    if (input === 'subTimeout') return 15 // https://github.com/awslabs/aws-mobile-appsync-sdk-js/issues/541
    if (input === undefined) return 4
    throw new Error(`Unexpected input to sleep(): '${input}'`)
  })()
  return new Promise((resolve) => setTimeout(resolve, sec * 1000))
}

/** Poll the given `target` function until EITHER
 *  - no jest.except()'s fail OR
 *  - maxDelay is reached
 */
const eventually = async (target, {initialDelay = 0, pollingDelay = 1, maxDelay = 10} = {} /* in seconds */) => {
  const start = Date.now() / 1000
  const forceStop = start + maxDelay
  let nextDelay = initialDelay
  let jestError
  while (Date.now() / 1000 < forceStop) {
    await sleep(nextDelay)
    try {
      return await target()
    } catch (err) {
      // Jest doesn't export JestAssertionError
      // https://github.com/facebook/jest/blob/v26.6.3/packages/expect/src/index.ts#L52
      if (err.constructor.name !== 'JestAssertionError') throw err
      jestError = err
    }
    nextDelay = pollingDelay
  }
  throw jestError || new Error('Target function never ran')
}

module.exports = {
  eventually,
  sleep,
}
