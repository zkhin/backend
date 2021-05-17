/* Misc utils functions for use in tests */

const jpeg = require('jpeg-js')

const {eventually} = require('./timing')
const {mutations, queries} = require('../schema')

const shortRandomString = () => Math.random().toString(36).substring(7)

const generateRandomJpeg = (width, height) => {
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

const deleteDefaultCard = async (client) => {
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

module.exports = {
  deleteDefaultCard,
  generateRandomJpeg,
  shortRandomString,
}
