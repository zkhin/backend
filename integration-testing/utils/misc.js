/* Misc utils functions for use in tests */

import jpeg from 'jpeg-js'
import path from 'path'

import {eventually} from './timing'
import {mutations, queries} from '../schema'

export const shortRandomString = () => Math.random().toString(36).substring(7)

export const generateRandomJpeg = (width, height) => {
  const buf = Buffer.alloc(width * height * 4)
  let i = 0
  while (i < buf.length) {
    buf[i++] = Math.floor(Math.random() * 256)
  }
  const imgData = {
    data: buf,
    width: width,
    height: height,
  }
  const quality = 50
  return jpeg.encode(imgData, quality).data
}

export const deleteDefaultCard = async (client) => {
  const cardId = await eventually(async () => {
    const {data} = await client.query({query: queries.self})
    expect(data.self.cards.items).toHaveLength(1)
    return data.self.cards.items[0].cardId
  })
  await client.mutate({mutation: mutations.deleteCard, variables: {cardId}})
  await eventually(async () => {
    const {data} = await client.query({query: queries.self})
    expect(data.self.cards.items).toHaveLength(0)
  })
}

export const repoRoot = path.resolve(new URL(import.meta.url).pathname, '../../../')
export const moduleRoot = path.resolve(new URL(import.meta.url).pathname, '../../')
export const fixturePath = (filename) => path.resolve(moduleRoot, 'fixtures', filename)
