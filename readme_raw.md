The get_data.py file contains a dictionary called "areas" that defines specific geographic areas of interest. Each area is represented by a key (the name of the area) and a value that is another dictionary containing the lower-left (ll) and upper-right (ur) coordinates of the area in latitude and longitude format.

# Configuration
ZOOM = "17"
MIN_DATE = "2006/01/01"
MAX_DATE = "2025/12/31"
TARGET_IMAGES = 100

The configuration section defines parameters for the data retrieval process. The ZOOM variable specifies the zoom level for the imagery, while MIN_DATE and MAX_DATE define the date range for the images to be retrieved. TARGET_IMAGES indicates the number of images to be collected for each area.

The script will use these configurations to query and download satellite imagery for the specified areas within the defined date range and zoom level, aiming to collect the target number of images for each area.

Note: The script will only retrieve images that have full coverage of the defined area, meaning that the entire area must be visible in the image for it to be considered valid. The tile size is determined by the zoom level, and the script will ensure that the images collected meet the criteria for full coverage based on the defined coordinates.

The more the zoom level, the larger the image size and more detailed the imagery will be, but it may also result in fewer images being available for the specified date range. Adjusting the zoom level and date range can help optimize the number of images collected while ensuring they meet the desired quality and coverage criteria.

Usage and further details on how to run the script and retrieve the data can be found here: https://github.com/Mbucari/GEHistoricalImagery

We can get the coordinates of the areas of interest in the /get_coordinates.html file, which provides a user-friendly interface for selecting and obtaining the latitude and longitude coordinates for the areas we want to target for imagery retrieval. This tool allows users to visually select the areas on a map and automatically generates the corresponding coordinates in the required format for use in the get_data.py script.