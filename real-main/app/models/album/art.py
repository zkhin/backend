from io import BytesIO
import math

from PIL import Image


def generate_basic_grid(image_data_buffers):
    """
    Given a 4, 9 or 16 images data buffers, generate a basic grid of those images.
    No zooming or croping of input images.
    Returns a in-memory buffer of jpeg image data.
    """
    assert len(image_data_buffers) in (4, 9, 16), f'Unexpected number of inputs: `{len(image_data_buffers)}`'

    # collect all the 1080p thumbs from all the post images
    images = []
    max_width, max_height = 0, 0
    for buf in image_data_buffers:
        image = Image.open(buf)
        max_width = max(max_width, image.size[0])
        max_height = max(max_height, image.size[1])
        images.append(image)

    # paste those thumbs together as a grid
    # Min size will be 4k since max_width and max_height come from 1080p thumbs
    stride = int(math.sqrt(len(image_data_buffers)))
    target_image = Image.new('RGB', (max_width * stride, max_height * stride))
    for row in range(0, stride):
        for column in range(0, stride):
            image = images[row * stride + column]
            width, height = image.size
            loc = (column * max_width + (max_width - width) // 2, row * max_height + (max_height - height) // 2)
            target_image.paste(image, loc)

    # convert to jpeg
    buf_out = BytesIO()
    target_image.save(buf_out, format='JPEG')
    buf_out.seek(0)
    return buf_out
