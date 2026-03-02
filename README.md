# NewYorker Package

## Network Requirements

Enable P2P for your devices. See [the documentation](https://info-beamer.com/doc/device-configuration#p2p). This
will allow faster asset transfers to your devices and allows devices to verify that they all use the correct system
time. The system time is important for any video wall setup, so make sure the devices can reach each other.

You can verify that by visiting a device detail page and check the P2P peer count.

Additionall this package requires port 4242 (incoming/outgoing) for both UDP/TCP. Unlike all communication made
by info-beamer, this communication is not encrypted and relies on a non-hostile network environment at the moment.
UDP is used again for device discovery for devices that are configured in the same "screen group". Some content
in a playlist is dynamic and requires to be the same on each screen of a "screen group", otherwise different
quadrants in a video wall might end up showing different content. Inter-node communication through a two-phase
commit protocol tries to ensure that all devices showing dynamic content have the exact same data available at
playback time.

## Setting up a video wall

Unconfigured screens show the complete content. So if you only have single screens (aka 1x1 video walls), you don't have to
configure anything. For each video wall installation that you want to use, create a new screen group. Choose the screen
layout and then add all devices. You can only select devices that are not yet part of another screen group.

## Preparing 4K Content

info-beamer, or more precisely the Raspberry Pi, cannot decode 4K content due to hardware limitations. This package
circumvents this limit by requiring content to be preprocessed. Each 4K content has to be prepared for playback. The result
are 5 assets for each 4K content. They have to be named according to this pattern:

```
video-file.mp4       - the downscaled 4K video in FullHD resolution
video-file-2x2-0.mp4 - the top left corner of the original 4K video
video-file-2x2-1.mp4 - the top right corner of the original 4K video
video-file-2x2-2.mp4 - the bottom left corner of the original 4K video
video-file-2x2-2.mp4 - the bottom right corner of the original 4K video
```

If you upload all five files, the playlist editor will automtically recognise this video as 4K and handle everything
for you.

### Images

If you have a 3840x2160 image, you have to convert it into 5 new images like this:

```
convert 4k-source.jpg -scale 1920x1080 image.jpg
convert 4k-source.jpg -crop 1920x1080 image-2x2-%d.jpg
```

The first command will downscale the complete 4K image to FullHD. This version of the image is then later used during
playback if the image is only shown on a single screen.

The second command will create 4 new images in FullHD resolution. Each of them is one of the 4 quadrants of the original
image. In a video wall installation, only a single image is rendered in each of the screen. Across all screens you get 4K
resolution as a result.

### Videos

Similar to images, videos also have to be preprocessed. The idea is exactly the same: One version of the original video is
downscaled to FullHD, while 4 other videos each consist the 4 quadrants of the original video.

```

ffmpeg -i 4k-source.mp4 -vf scale=1920:1080 -c:a copy video.mp4
ffmpeg -i 4k-source.mp4 -filter:v "crop=1920:1080:0:0"       -c:a copy video-2x2-0.mp4
ffmpeg -i 4k-source.mp4 -filter:v "crop=1920:1080:1920:0"    -c:a copy video-2x2-1.mp4
ffmpeg -i 4k-source.mp4 -filter:v "crop=1920:1080:0:1080"    -c:a copy video-2x2-2.mp4
ffmpeg -i 4k-source.mp4 -filter:v "crop=1920:1080:1920:1080" -c:a copy video-2x2-3.mp4
```

# Versions

## Version 0.7

 * First DressFM Page

## Version 0.6

 * Lifestyle Page finished
 * Added matching products on product page

## Version 0.5

 * Uses new `randomCollectionProducts` API call and adds the ability to filter by brands.

## Version 0.4

 * Move "global settings" node into root
 * Dynamic pages now retain their fetched data if moved within the playlist thanks to using a UUID for each playlist item.

## Version 0.3

 * Added initial Lifestyle page

## Version 0.2

 * Added duration in playlist editor
 * Click an asset to append to the playlist

## Version 0.1

 * Initial playlist editor, screen group editor and proof of concept "Produktinformation" asset implemented.
