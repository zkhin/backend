import {v4 as uuidv4} from 'uuid'

import {cognito, eventually, generateRandomJpeg} from '../../utils'
import {mutations, queries} from '../../schema'

let anonClient
const imageBytes = generateRandomJpeg(300, 200)
const imageData = new Buffer.from(imageBytes).toString('base64')
const loginCache = new cognito.AppSyncLoginCache()

beforeAll(async () => {
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
  loginCache.addCleanLogin(await cognito.getAppSyncLogin())
})
beforeEach(async () => await loginCache.clean())
afterAll(async () => await loginCache.reset())
afterEach(async () => {
  if (anonClient) await anonClient.mutate({mutation: mutations.deleteUser})
  anonClient = null
})

test('Add post with keywords attribute - serach keywords', async () => {
  const {client: ourClient} = await loginCache.getCleanLogin()
  const {client: theirClient} = await loginCache.getCleanLogin()

  const [postId1, postId2] = [uuidv4(), uuidv4()]
  let keywords = ['mine', 'bird', 'tea', 'hera']

  // Add two posts
  await ourClient
    .mutate({mutation: mutations.addPost, variables: {postId: postId1, imageData, keywords}})
    .then(({data: {addPost: post}}) => {
      expect(post.postId).toBe(postId1)
      expect(post.keywords.sort()).toEqual(keywords.sort())
    })

  keywords = ['tea', 'bird', 'here']
  await theirClient
    .mutate({mutation: mutations.addPost, variables: {postId: postId2, imageData, keywords}})
    .then(({data: {addPost: post}}) => {
      expect(post.postId).toBe(postId2)
      expect(post.keywords.sort()).toEqual(keywords.sort())
    })

  let searchKeyword = 'her'
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.searchKeywords, variables: {keyword: searchKeyword}})
    expect(data.searchKeywords.sort()).toEqual(['here', 'hera'].sort())
  })

  searchKeyword = 'shir'
  await ourClient
    .query({query: queries.searchKeywords, variables: {keyword: searchKeyword}})
    .then(({data: {searchKeywords: keywords}}) => {
      expect(keywords).toEqual([])
    })

  searchKeyword = 'min'
  await ourClient
    .query({query: queries.searchKeywords, variables: {keyword: searchKeyword}})
    .then(({data: {searchKeywords: keywords}}) => {
      expect(keywords).toEqual(['mine'])
    })
})

test('Remove post - serach keywords', async () => {
  const {client: ourClient} = await loginCache.getCleanLogin()
  const {client: theirClient} = await loginCache.getCleanLogin()

  const [postId1, postId2] = [uuidv4(), uuidv4()]
  let keywords = ['mine', 'bird', 'tea', 'hera']

  // Add two posts
  await ourClient
    .mutate({mutation: mutations.addPost, variables: {postId: postId1, imageData, keywords}})
    .then(({data: {addPost: post}}) => {
      expect(post.postId).toBe(postId1)
      expect(post.keywords.sort()).toEqual(keywords.sort())
    })

  keywords = ['tea', 'bird', 'here']
  await theirClient
    .mutate({mutation: mutations.addPost, variables: {postId: postId2, imageData, keywords}})
    .then(({data: {addPost: post}}) => {
      expect(post.postId).toBe(postId2)
      expect(post.keywords.sort()).toEqual(keywords.sort())
    })

  let searchKeyword = 'min'
  await ourClient
    .query({query: queries.searchKeywords, variables: {keyword: searchKeyword}})
    .then(({data: {searchKeywords: keywords}}) => {
      expect(keywords).toEqual(['mine'])
    })

  // Remove our post
  await ourClient
    .mutate({mutation: mutations.deletePost, variables: {postId: postId1}})
    .then(({data: {deletePost: post}}) => {
      expect(post.postId).toBe(postId1)
      expect(post.postStatus).toBe('DELETING')
    })

  searchKeyword = 'min'
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.searchKeywords, variables: {keyword: searchKeyword}})
    expect(data.searchKeywords).toEqual([])
  })

  searchKeyword = 'her'
  await eventually(async () => {
    const {data} = await ourClient.query({query: queries.searchKeywords, variables: {keyword: searchKeyword}})
    expect(data.searchKeywords).toEqual(['here'])
  })
})
