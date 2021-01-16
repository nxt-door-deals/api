from fastapi.responses import HTMLResponse

from . import router


@router.get("/", response_class=HTMLResponse)
def return_index_html():
    return """
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <meta name="robots" content="noindex,nofollow" />
            <meta
                property="og:image"
                content="https://nxt-door-deals-test.s3.ap-south-1.amazonaws.com/site-images/icon.png"
            />
            <meta property="og:image:width" content="256" />
            <meta property="og:image:height" content="256" />
            <meta
                property="og:title"
                content="NXT Door Deals | Your neighbourhood marketplace"
            />
            <meta
                property="og:description"
                content="Your one-stop shop to find amazing deals within your apartment complex, gated community or housing society."
            />
            <title>NXT Door Deals | Your neighbourhood marketplace</title>
            <link rel="icon" href="https://nxt-door-deals.s3.ap-south-1.amazonaws.com/site-images/favicon.ico" />
            <style>
                html {
                    box-sizing: border-box;
                    margin: 0;
                    padding: 0;
                }

                body {
                    text-align: center;
                }

                img {
                    margin-top: 50px;
                }

                p {
                    font-family: 'Franklin Gothic Medium', 'Arial Narrow', Arial, sans-serif;
                    font-size: 3em;
                    color: #550052;
                    padding: 10px;
                }

                a {
                    text-decoration: none;
                    color: #9F7AEA;
                }
            </style>
        </head>
        <body>
            <img src="https://nxt-door-deals-test.s3.ap-south-1.amazonaws.com/site-images/icon.png" height="200px" alt="Brand Icon"/>
            <p>Welcome to <strong>nxt-door deals</strong>!</p>
            <p>Proceed to the website - <a href="https://nxtdoordeals.com">nxtdoordeals.com</a></p>
        </body>
        </html>
    """
