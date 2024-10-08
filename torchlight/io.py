# Sources
# https://github.com/greentfrapp/lucent/blob/dev/lucent/misc/io/serialize_array.py
# https://github.com/greentfrapp/lucent/blob/dev/lucent/misc/io/showing.py
from .utils import create_simple_logger, T, A, DEVICE

import torch
import base64
import numpy as np
import PIL.Image
from io import BytesIO
import IPython.display
from string import Template
from typing import List, Optional, Tuple, Union

logger = create_simple_logger(__name__)


def tensor_image_to_numpy_array(tensor_image: T) -> A:
    """Convert a PyTorch tensor image to a NumPy array.

    Parameters
    ----------
    tensor_image : torch.Tensor
        The tensor image to convert.

    Returns
    -------
    np.ndarray
        The NumPy array of the tensor image.
    """
    return tensor_image.cpu().detach().numpy().transpose(1, 2, 0)


def normalize_array(array: A, domain: Optional[Tuple[float, float]] = None) -> A:
    """Given an arbitrary rank-3 NumPy array, produce one representing an image.

    This ensures the resulting array has a dtype of uint8 and a domain of 0-255.

    Parameters
    ----------
    array : np.ndarray
        The array to normalize.
    domain : Tuple[float, float], optional
        The domain of the input array, by default None. If None, the domain will be inferred from the array.

    Returns
    -------
    np.ndarray
        The normalized array.
    """
    # first copy the input so we're never mutating the user's data
    array = np.array(array)
    # squeeze helps both with batch=1 and B/W and PIL's mode inference
    array = np.squeeze(array)
    assert len(array.shape) <= 3
    assert np.issubdtype(array.dtype, np.number)
    assert not np.isnan(array).any()

    low, high = np.min(array), np.max(array)
    if domain is None:
        message = f"No domain specified, normalizing from measured range (~{low:.2f}, ~{high:.2f})."
        logger.debug(message)
        domain = (low, high)

    # clip values if domain was specified and array contains values outside of it
    if low < domain[0] or high > domain[1]:
        message = f"Clipping domain from ({low:.2f}, {high:.2f}) to ({domain[0]}, {domain[1]})."
        logger.debug(message)
        array = array.clip(*domain)

    min_value, max_value = np.iinfo(np.uint8).min, np.iinfo(np.uint8).max  # 0, 255
    # convert signed to unsigned if needed
    if np.issubdtype(array.dtype, np.inexact):
        offset = domain[0]
        if offset != 0:
            array -= offset
        if domain[0] != domain[1]:
            scalar = max_value / (domain[1] - domain[0])
            if scalar != 1:
                array *= scalar

    return array.clip(min_value, max_value).astype(np.uint8)


def _serialize_normalized_array(
    array: A, fmt: str = "png", quality: int = 70
) -> BytesIO:
    """Given a normalized array, returns byte representation of image encoding.

    Parameters
    ----------
    array : np.ndarray
        The normalized array of dtype uint8 and range 0 to 255
    fmt : str, optional
        The desired file format, by default 'png'
    quality : int, optional
        The compression quality from 0 to 100 for lossy formats, by default 70

    Returns
    -------
    BytesIO
        The image data as a BytesIO buffer.
    """
    dtype = array.dtype
    assert np.issubdtype(dtype, np.unsignedinteger)
    assert np.max(array) <= np.iinfo(dtype).max
    assert array.shape[-1] > 1  # array dims must have been squeezed

    image = PIL.Image.fromarray(array)
    image_bytes = BytesIO()
    image.save(image_bytes, fmt, quality=quality)
    image_data = image_bytes.getvalue()
    return image_data


def numpy_image_to_video(
    images: List[A],
    fps: int = 5,
    filename: str = "output.mp4",
    domain: Optional[Tuple[float, float]] = None,
) -> None:
    """Save a list of images as an MP4 video.

    Parameters
    ----------
    images : List[np.ndarray]
        The list of images to save.
    fps : int, optional
        The frames per second of the video, by default 5.
    filename : str, optional
        The path to save the video, by default 'output.mp4'.
    """
    images = [normalize_array(image, domain=domain) for image in images]
    import cv2

    h, w, _ = images[0].shape
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(filename, fourcc, fps, (w, h))

    for image in images:
        # change from RGB to BGR, as OpenCV expects BGR
        image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
        out.write(image)

    out.release()


def numpy_image_to_gif(
    images: List[A],
    filename: str = "output.gif",
    domain: Optional[Tuple[float, float]] = None,
):
    """Saves a list of images as a GIF.

    Parameters
    ----------
    images : List[np.ndarray]
        The list of images to save.
    filename : str, optional
        The path to save the GIF, by default 'output.gif'.
    """
    import PIL.Image

    images = [normalize_array(image, domain=domain) for image in images]

    images = [PIL.Image.fromarray(image) for image in images]
    images[0].save(
        filename,
        save_all=True,
        append_images=images[1:],
        duration=100,
        loop=0,
    )


def save_images(
    images: List[A],
    save_path: str,
    domain: Optional[Tuple[float, float]] = None,
    fps: int = 5,
) -> str:
    """Save a list of images as numpy arrays or PNG files.

    Parameters
    ----------
    images : List[np.ndarray]
        The list of images to save.
    save_path : str
        The path to save the images. The supported file formats are .npy, .png, .mp4 and .gif.

        - 'npy': Save the images as a single numpy array.
        - 'png': Save the images as individual PNG files. If a single image is provided, the name will be the same as the path. If multiple images are provided, the name will be the path with an index appended. (e.g. 'path_0.png', 'path_1.png', etc.)
        - 'mp4': Save the images as an MP4 video. The path should include the file extension.
        - 'gif': Save the images as a GIF. The path should include the file extension.

    domain : Tuple[float, float], optional
        The domain of the input array, by default None. If None, the domain will be inferred from the array.
    fps : int, optional
        The frames per second of the video, by default 5. Only used a video is saved.
    """
    save_type = save_path.split(".")[-1]
    images = [normalize_array(image, domain) for image in images]
    if save_type == "npy":
        images_array = np.stack(images)
        np.save(save_path, images_array)

    elif save_type == "png":
        if ".png" in save_path:
            save_path = save_path.replace(".png", "")
        if len(images) == 1:
            image = PIL.Image.fromarray(images[0])
            image.save(f"{save_path}.png")
        else:
            for i, image in enumerate(images):
                image = PIL.Image.fromarray(image)
                image.save(f"{save_path}_{i}.png")
    elif save_type == "mp4":
        numpy_image_to_video(images, filename=save_path, fps=fps)
    elif save_type == "gif":
        numpy_image_to_gif(images, filename=save_path)
    else:
        raise ValueError(
            f"Unsupported save type: {save_type}. Only 'npy', 'png', 'mp4' and 'gif' are supported."
        )


def load_gif(gif_path: str) -> List[A]:
    """Load a GIF file as a list of images.

    Parameters
    ----------
    gif_path : str
        The path to the GIF file.

    Returns
    -------
    List[np.ndarray]
        The list of images.
    """
    images = []
    gif = PIL.Image.open(gif_path)
    for frame in range(gif.n_frames):
        gif.seek(frame)
        image = np.array(gif)
        images.append(image)
    return images


def load_images(
    image_paths: Union[str, List[str]],
    return_as_numpy: bool = False,
) -> List[A]:
    """Load a list of images from file paths.

    Parameters
    ----------
    image_paths :  Union[str, List[str]],
        The path(s) to the images to load. The supported file formats are .npy, .png and .gif.

    Returns
    -------
    List[np.ndarray]
        The list of images.
    """
    if isinstance(image_paths, str):
        image_paths = [image_paths]
    images = []
    for path in image_paths:
        if path.endswith(".npy"):
            images_: A = np.load(path)
            # convert to list of images if multiple images are saved in a single numpy array
            if len(images_.shape) == 4:
                images_ = images_.tolist()
                images_ = [np.array(image) for image in images_]
            else:
                images_ = [images_]
            images.extend(images_)
        elif path.endswith(".png"):
            image = PIL.Image.open(path)
            image: A = np.array(image)
            images.append(image)
        elif path.endswith(".gif"):
            images_ = load_gif(path)
            images.extend(images_)
        else:
            raise ValueError(
                f"Unsupported file format: {path}. Only .npy, .png and .gif files are supported."
            )
    if return_as_numpy:
        images = np.stack(images)
    return images


def serialize_array(
    array: A,
    domain: Optional[Tuple[float, float]] = None,
    fmt: str = "png",
    quality: int = 70,
) -> BytesIO:
    """Given an arbitrary rank-3 NumPy array, returns the byte representation of the encoded image.

    Parameters
    ----------
    array : np.ndarray
        The normalized array of dtype uint8 and range 0 to 255
    domain : Tuple[float, float], optional
        The domain of the input array, by default None. If None, the domain will be inferred from the array.
    fmt : str, optional
        The desired file format, by default 'png'
    quality : int, optional
        The compression quality from 0 to 100 for lossy formats, by default 70
    """
    normalized = normalize_array(array, domain=domain)
    return _serialize_normalized_array(normalized, fmt=fmt, quality=quality)


JS_ARRAY_TYPES = {
    "int8",
    "int16",
    "int32",
    "uint8",
    "uint16",
    "uint32",
    "float32",
    "float64",
}


def array_to_jsbuffer(array: A) -> str:
    """Serialize 1d NumPy array to JS TypedArray.

    Data is serialized to base64-encoded string, which is much faster
    and memory-efficient than json list serialization.

    Parameters
    ----------
    array : np.ndarray
        The array to serialize.

    Returns
    -------
    str
        The serialized array as a JS TypedArray.
    """

    if array.ndim != 1:
        raise TypeError("Only 1d arrays can be converted JS TypedArray.")
    if array.dtype.name not in JS_ARRAY_TYPES:
        raise TypeError("Array dtype not supported by JS TypedArray.")
    js_type_name = array.dtype.name.capitalize() + "Array"
    data_base64 = base64.b64encode(array.tobytes()).decode("ascii")
    code = """
        (function() {
            const data = atob("%s");
            const buf = new Uint8Array(data.length);
            for (var i=0; i<data.length; ++i) {
                buf[i] = data.charCodeAt(i);
            }
            var array_type = %s;
            if (array_type == Uint8Array) {
                return buf;
            }
            return new array_type(buf.buffer);
        })()
    """ % (
        data_base64,
        js_type_name,
    )
    return code


def _display_html(html_str):
    IPython.display.display(IPython.display.HTML(html_str))


def _image_url(
    array: A,
    fmt: str = "png",
    mode: str = "data",
    quality: int = 90,
    domain: Optional[Tuple[float, float]] = None,
) -> str:
    """Create a data URL representing an image from a PIL.Image.

    Parameters
    ----------
    array : np.ndarray
        The array to convert to an image.
    fmt : str, optional
        The image format, by default 'png'
    mode : str, optional
        The mode of the image, by default 'data'
    quality : int, optional
        The compression quality from 0 to 100 for lossy formats, by default 90
    domain : Tuple[float, float], optional
        The domain of the input array, by default None. If None, the domain will be inferred from the array.

    Returns
    -------
    str
        The URL of the image.
    """
    supported_modes = "data"
    if mode not in supported_modes:
        message = "Unsupported mode '%s', should be one of '%s'."
        raise ValueError(message, mode, supported_modes)

    image_data = serialize_array(array, fmt=fmt, quality=quality, domain=domain)
    base64_byte_string = base64.b64encode(image_data).decode("ascii")
    return "data:image/" + fmt.upper() + ";base64," + base64_byte_string


def _image_html(
    array: A,
    width: Optional[int] = None,
    domain: Optional[Tuple[float, float]] = None,
    fmt: str = "png",
    title: Optional[str] = "",
) -> str:
    url = _image_url(array, domain=domain, fmt=fmt)
    style = "image-rendering: pixelated;"
    if width is not None:
        style += "width: {width}px;".format(width=width)
    if title:
        title_h = "<h4>{title}</h4>".format(title=title)
    else:
        title_h = ""
    return f"""{title_h}<img src="{url}" style="{style}" alt={title}>"""


def show_image(
    array: A,
    domain: Optional[Tuple[float, float]] = None,
    width: Optional[int] = None,
    fmt: str = "png",
    title: Optional[str] = "",
) -> None:
    """Display an image.

    Parameters
    ----------
    array : np.ndarray
        The array to display.
    domain : Tuple[float, float], optional
        The domain of the input array, by default None. If None, the domain will be inferred from the array.
    width : Optional[int], optional
        The width of the output image, by default None. If None, the size will be unchanged.
    fmt : str, optional
        The image format, by default 'png'
    title : Optional[str], optional
        The title of the image, by default ""
    """
    rank = len(array.shape)
    if rank == 3:
        if width is None:
            width = int(
                array.shape[1] * 1.2
            )  # default to the 120% of width of the image since the image will be wrapped in a div
        logger.debug("Displaying a single image.")
        # a single image
        image_html = _image_html(
            array, width=width, domain=domain, fmt=fmt, title=title
        )
        final_html = f"""<div style="width:{width}px;text-align:center;">
        <figure>
        {image_html}
        </figure>
        </div>
        """
        _display_html(final_html)
    elif rank == 4:
        logger.debug("Displaying a sequence of images.")
        # a sequence of images
        images = [array[i] for i in range(array.shape[0])]
        show_images(
            images=images,
            labels=[str(i) for i in range(len(images))],
            domain=domain,
            width=width,
            fmt=fmt,
            n_rows=1,
        )


def _create_image_table(
    images: List[A],
    labels: Optional[List[str]] = None,
    domain: Optional[Tuple[float, float]] = None,
    width: Optional[int] = None,
    fmt: str = "png",
    n_rows: Optional[int] = None,
):
    """Create an HTML table of images.

     Parameters
    ----------
    images : List[np.ndarray]
        A list of NumPy images representing images.
    labels : Optional[List[str]], optional
        A list of strings to label each image, by default None. If None, the index will be shown.
    domain : Tuple[float, float], optional
        The domain of the input array, by default None. If None, the domain will be inferred from the array.
    width : Optional[int], optional
        The width of the output image, by default None. If None, the size will be unchanged.
    n_rows : Optional[int], optional
        The number of columns in the output table, by default None. If None, the number of columns will be the square root of the number of images.

    Returns
    -------
    str
        The HTML table of images.
    """
    n_rows = n_rows or np.ceil(np.sqrt(len(images))).astype(int)
    n_cols = len(images) // n_rows
    if n_rows * n_cols < len(images):
        n_rows += 1

    images_html = """<style>
    td:hover {
        transition: transform 0.5s;
        transform: scale(1.1);
        }
    </style>
    <table style='border-collapse: collapse;'>
    """
    for i in range(n_rows):
        images_html += "<tr>"
        for j in range(n_cols):
            idx = i * n_cols + j
            if idx < len(images):
                image_html = _image_html(
                    images[idx], width=width, domain=domain, fmt=fmt, title=labels[idx]
                )
                images_html += f"<td style='text-align: center;'>{image_html}</td>"
        images_html += "</tr>"
    images_html += "</table>"
    return images_html


def show_images(
    images: List[A],
    labels: Optional[List[str]] = None,
    domain: Optional[Tuple[float, float]] = None,
    width: Optional[int] = None,
    fmt: str = "png",
    n_rows: int = 1,
) -> None:
    """Display a list of images with optional labels.

    Parameters
    ----------
    images : List[np.ndarray]
        A list of NumPy images representing images.
    labels : Optional[List[str]], optional
        A list of strings to label each image, by default None. If None, the index will be shown.
    domain : Tuple[float, float], optional
        The domain of the input array, by default None. If None, the domain will be inferred from the array.
    width : Optional[int], optional
        The width of the output image, by default None. If None, the size will be unchanged.
    n_rows : int, optional
        The number of columns in the output table, by default 1.
    """
    string = '<div style="display: flex; flex-direction: row;">'
    labels = labels or list(range(1, len(images) + 1))
    images_html = _create_image_table(
        images=images, labels=labels, domain=domain, width=width, fmt=fmt, n_rows=n_rows
    )
    string += f"""<div style="margin-right:10px; margin-top: 4px;">
                        {images_html}
                    </div>"""
    string += "</div>"
    _display_html(string)


def animate_sequence(
    sequence: Union[A, List[A]],
    domain: Optional[Tuple[float, float]] = None,
    fmt: str = "png",
    time_in_seconds: Optional[int] = None,
    frames_per_second: int = 5,
    title: Optional[str] = "",
) -> None:
    """Animate a sequence of images.

    Parameters
    ----------
    sequence : np.ndarray
        The sequence of images to animate.
    domain : Tuple[float, float], optional
        The domain of the input array, by default None. If None, the domain will be inferred from the array.
    fmt : str, optional
        The image format, by default 'png'
    time_in_seconds : Optional[int], optional
        The time in seconds to display the animation, by default None. If None, the time will be calculated from the number of frames and the frames per second.
    frames_per_second : int, optional
        The frames per second of the animation, by default 5.
    """
    if isinstance(sequence, list):
        sequence = np.array(sequence)

    steps, height, width, _ = sequence.shape
    sequence = np.concatenate(sequence, 1)
    if time_in_seconds is None:
        time_in_seconds = steps / frames_per_second

    code = Template(
        """
    <style> 
        #animation {
            width: ${width}px;
            height: ${height}px;
            background: url('$image_url') left center;
            animation: play ${time_in_seconds}s steps($steps) infinite alternate;
        }
        @keyframes play {
            100% { background-position: -${sequence_width}px; }
        }
    </style>
    <h4>${title}</h4>
    <div id='animation'>
    </div>
    """
    ).substitute(
        image_url=_image_url(sequence, domain=domain, fmt=fmt),
        sequence_width=width * steps,
        width=width,
        height=height,
        steps=steps,
        time_in_seconds=time_in_seconds,
        title=title,
    )
    _display_html(code)


def load_image(
    path: str,
    h: Optional[int] = None,
    w: Optional[int] = None,
    return_as_tensor: bool = True,
    device: str = DEVICE,
):
    """Loads an image from a given path and resizes it to the given dimensions. Returns the image as a numpy array."""
    image = PIL.Image.open(path)
    if h is not None or w is not None:
        h = h or image.size[1]
        w = w or image.size[0]

        image = image.resize((w, h))

    image = np.array(image)
    image = image / 255.0
    if not return_as_tensor:
        return image

    image = (
        torch.tensor(np.transpose(image, [2, 0, 1]))
        .unsqueeze(0)  # batch dimension
        .float()
        .to(device)
    )
    return image
