## json schema for media requests

```json
{
    "yt": [
        {
            "type": "single",
            "url": "https://www.youtube.com/watch?v=3JZ_D3ELwOQ",
        },
        {
            "type": "playlist",
            "url": "https://www.youtube.com/playlist?list=PLZQGTj6bZlZ8Q1J1Z1vJ1aZJ1J1Z1J1Z1",
        },
        {
            "type": "short",
            "url": "https://www.youtube.com/short/UCJFp8uSYCjXOMnkUyb3CQ3Q",
        }
    ],
    "gip": [
        {
            "type": "single",
            "url": "https://www.bbc.co.uk/iplayer/episode/p00vfknq/doctor-who-19631996-season-16-the-ribos-operation-part-1"
        }
    ]
}
```

## Building the JSON Payload

1. The cliptube clipboard watcher will watch for BBC Iplayer and Youtube URLs
1. Depending on the type of URL it will build sections of the payload as above
1. Once complete the payload will be sent to `druidmedia` in the directory
   `~/.cliptube/' as a numerically indexed file (e.g. `~/.cliptube/00.json`)
1. The file index will increment for each new payload, resetting at 99
