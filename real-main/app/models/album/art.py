import io
import math

import PIL.Image as Image


def generate_basic_grid(image_data_buffers):
    """
    Given a square number (4, 9 or 16) of image data buffers, generate an buffer with a
    jpeg-encoded grid of those images.

    No zooming or croping of input images.
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
    buf_out = io.BytesIO()
    target_image.save(buf_out, format='JPEG', quality=100)
    buf_out.seek(0)
    return buf_out


def generate_zoomed_grid(image_data_buffers):
    """
    Given a square number (4, 9 or 16) of image data buffers, generate an buffer with a
    jpeg-encoded grid of those images.

    Zoom in or out and crop each image as needed so that it fills its cell perfectly.
    """
    assert len(image_data_buffers) in (4, 9, 16), f'Unexpected number of inputs: `{len(image_data_buffers)}`'

    output_width, output_height = 3840, 2160
    stride = int(math.sqrt(len(image_data_buffers)))
    cell_width, cell_height = output_width // stride, output_height // stride

    # collect and resize (zoom in or out as needed so each image fills its cell)
    images = []
    for buf in image_data_buffers:
        image = Image.open(buf)
        image_width, image_height = image.size

        # comparing aspect ratios without rounding errors
        if image_width * cell_height > image_height * cell_width:
            # image is wider than cell
            new_image_width = image_height * cell_width / cell_height
            margin = (image_width - new_image_width) / 2
            box = (margin, 0, image_width - margin, image_height)
        elif image_width * cell_height < image_height * cell_width:
            # image is taller than cell
            new_image_height = image_width * cell_height / cell_width
            margin = (image_height - new_image_height) / 2
            box = (0, margin, image_width, image_height - margin)
        else:
            # aspect ratios equal
            box = None

        if image_width != cell_width or image_height != cell_height:
            image = image.resize((cell_width, cell_height), box=box, resample=Image.LANCZOS)

        images.append(image)

    # paste those thumbs together as a grid
    # Min size will be 4k since max_width and max_height come from 1080p thumbs
    target_image = Image.new('RGB', (output_width, output_height))
    for row in range(0, stride):
        for column in range(0, stride):
            image = images[row * stride + column]
            loc = (column * cell_width, row * cell_height)
            target_image.paste(image, loc)

    # convert to jpeg
    buf_out = io.BytesIO()
    target_image.save(buf_out, format='JPEG', quality=100)
    buf_out.seek(0)
    return buf_out
