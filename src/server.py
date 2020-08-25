import logging

from flask import Blueprint, current_app

from util import render_template_wrapper

server = Blueprint('server', __name__)
logger = logging.getLogger(__name__)


@server.route('/', methods=['GET'])
def home():
    provinces_geojson = current_app.config["PROVINCES_GEOJSON_RAW"]
    return render_template_wrapper("index.html", source=provinces_geojson)
