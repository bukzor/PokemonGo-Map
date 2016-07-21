# -*- coding: utf-8 -*-
import sqlite3

import flask
from flask import Flask, render_template
from flask_googlemaps import GoogleMaps
from flask_googlemaps import icons
import os
import re
import sys
import struct
import json
import requests
import argparse
import getpass
import werkzeug.serving
import pokemon_pb2
import time
from google.protobuf.internal import encoder
from google.protobuf.message import DecodeError
from datetime import datetime
from geopy.geocoders import GoogleV3
from gpsoauth import perform_master_login, perform_oauth
from geopy.exc import GeocoderTimedOut, GeocoderServiceError
from requests.packages.urllib3.exceptions import InsecureRequestWarning
from requests.adapters import ConnectionError
from requests.models import InvalidURL
from transform import *

requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

API_URL = 'https://pgorelease.nianticlabs.com/plfe/rpc'
LOGIN_URL = \
    'https://sso.pokemon.com/sso/login?service=https://sso.pokemon.com/sso/oauth2.0/callbackAuthorize'
LOGIN_OAUTH = 'https://sso.pokemon.com/sso/oauth2.0/accessToken'
APP = 'com.nianticlabs.pokemongo'

with open('credentials.json') as file:
	credentials = json.load(file)

PTC_CLIENT_SECRET = credentials.get('ptc_client_secret', None)
ANDROID_ID = credentials.get('android_id', None)
SERVICE = credentials.get('service', None)
CLIENT_SIG = credentials.get('client_sig', None)
GOOGLEMAPS_KEY = credentials.get('gmaps_key', None)

SESSION = requests.session()
SESSION.headers.update({'User-Agent': 'Niantic App'})
SESSION.verify = False

with open('config.json') as config:
    config = json.load(config)
    global_password = config['password']
    global_username = config['username']
    location = config['location']

global_token = None
access_token = None
DEBUG = True
VERBOSE_DEBUG = False  # if you want to write raw request/response to the console
COORDS_LATITUDE = 0
COORDS_LONGITUDE = 0
COORDS_ALTITUDE = 0
FLOAT_LAT = 0
FLOAT_LONG = 0
NEXT_LAT = 0
NEXT_LONG = 0
auto_refresh = 0
default_zoom = 0
pokemons = {}
gyms = {}
pokestops = {}
numbertoteam = {  # At least I'm pretty sure that's it. I could be wrong and then I'd be displaying the wrong owner team of gyms.
    0: 'Gym',
    1: 'Mystic',
    2: 'Valor',
    3: 'Instinct',
}
origin_lat, origin_lon = None, None
is_ampm_clock = False


def debug(message):
    if DEBUG:
        print '[-] {}'.format(message)


def time_left(ms):
    s = ms / 1000
    (m, s) = divmod(s, 60)
    (h, m) = divmod(m, 60)
    return (h, m, s)


def retrying_set_location(location_name):
    """
    Continue trying to get co-ords from Google Location until we have them
    :param location_name: string to pass to Location API
    :return: None
    """

    while True:
        try:
            set_location(location_name)
            return
        except (GeocoderTimedOut, GeocoderServiceError), e:
            debug(
                'retrying_set_location: geocoder exception ({}), retrying'.format(
                    str(e)))
        time.sleep(1.25)


def set_location(location_name):
    geolocator = GoogleV3()
    prog = re.compile('^(\-?\d+(\.\d+)?),\s*(\-?\d+(\.\d+)?)$')
    global origin_lat
    global origin_lon
    if prog.match(location_name):
        local_lat, local_lng = [float(x) for x in location_name.split(",")]
        alt = 0
        origin_lat, origin_lon = local_lat, local_lng
    else:
        loc = geolocator.geocode(location_name)
        origin_lat, origin_lon = local_lat, local_lng = loc.latitude, loc.longitude
        alt = loc.altitude
        print '[!] Your given location: {}'.format(loc.address.encode('utf-8'))

    print('[!] lat/long/alt: {} {} {}'.format(local_lat, local_lng, alt))
    set_location_coords(local_lat, local_lng, alt)


def set_location_coords(lat, long, alt):
    global COORDS_LATITUDE, COORDS_LONGITUDE, COORDS_ALTITUDE
    global FLOAT_LAT, FLOAT_LONG
    FLOAT_LAT = lat
    FLOAT_LONG = long
    COORDS_LATITUDE = f2i(lat)  # 0x4042bd7c00000000 # f2i(lat)
    COORDS_LONGITUDE = f2i(long)  # 0xc05e8aae40000000 #f2i(long)
    COORDS_ALTITUDE = f2i(alt)


def get_location_coords():
    return (COORDS_LATITUDE, COORDS_LONGITUDE, COORDS_ALTITUDE)


def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-a', '--auth_service', type=str.lower, help='Auth Service', default='ptc')
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument(
        '-i', '--ignore', help='Comma-separated list of Pokémon names or IDs to ignore')
    group.add_argument(
        '-o', '--only', help='Comma-separated list of Pokémon names or IDs to search')
    parser.add_argument(
        "-ar",
        "--auto-refresh",
        help="Enables an autorefresh that behaves the same as a page reload. " +
             "Needs an integer value for the amount of seconds")
    parser.add_argument(
        '-H',
        '--host',
        help='Set web server listening host',
        default='127.0.0.1')
    parser.add_argument(
        '-P',
        '--port',
        type=int,
        help='Set web server listening port',
        default=5000)
    parser.add_argument(
        '-z',
        '--zoom',
        help='The default map zoom level on open.  (Default %(default)s)',
        default=15,
        type=int)
    return parser.parse_args()

def main():
    full_path = os.path.realpath(__file__)
    (path, filename) = os.path.split(full_path)

    args = get_args()

    if args.auth_service not in ['ptc', 'google']:
        print '[!] Invalid Auth service specified'
        return

    print('[+] Locale is ' + args.locale)
    pokemonsJSON = json.load(
        open(path + '/locales/pokemon.' + args.locale + '.json'))

    if args.debug:
        global DEBUG
        DEBUG = True
        print '[!] DEBUG mode on'

    # only get location for first run
    if not (origin_lat and origin_lon):
        retrying_set_location(location)

    if args.auto_refresh:
        global auto_refresh
        auto_refresh = int(args.auto_refresh) * 1000

    if args.ampm_clock:
    	global is_ampm_clock
    	is_ampm_clock = True

    global default_zoom
    default_zoom = args.zoom

    ignore = []
    only = []
    if args.ignore:
        ignore = [i.lower().strip() for i in args.ignore.split(',')]
    elif args.only:
        only = [i.lower().strip() for i in args.only.split(',')]


def create_app():
    app = Flask(__name__, template_folder='templates')

    GoogleMaps(app, key=GOOGLEMAPS_KEY)
    return app


app = create_app()


@app.route('/data')
def data():
    """ Gets all the PokeMarkers via REST """
    return flask.jsonify(get_pokemarkers())

@app.route('/raw_data')
def raw_data():
    """ Gets raw data for pokemons/gyms/pokestops via REST """
    return flask.jsonify(pokemons=pokemons, gyms=gyms, pokestops=pokestops)


@app.route('/config')
def config():
    """ Gets the settings for the Google Maps via REST"""
    center = {
        'lat': origin_lat,
        'lng': origin_lon,
        'zoom': default_zoom,
        'identifier': "fullmap"
    }
    return flask.jsonify(center)


@app.route('/')
def fullmap():
    if 'refresh' in flask.request.args:
        auto_refresh_interval = int(flask.request.args['refresh']) * 1000
    else:
        auto_refresh_interval = auto_refresh
    return render_template(
        'example_fullmap.html',
        key=GOOGLEMAPS_KEY,
        auto_refresh=auto_refresh_interval,
    )


@app.route('/next_loc')
def next_loc():
    global NEXT_LAT, NEXT_LONG

    lat = flask.request.args.get('lat', '')
    lon = flask.request.args.get('lon', '')
    if not (lat and lon):
        print('[-] Invalid next location: %s,%s' % (lat, lon))
    else:
        print('[+] Saved next location as %s,%s' % (lat, lon))
        NEXT_LAT = float(lat)
        NEXT_LONG = float(lon)
        return 'ok'


def get_pokemarkers():
    pokeMarkers = [{
        'icon': icons.dots.red,
        'lat': origin_lat,
        'lng': origin_lon,
        'infobox': "Start position",
        'type': 'custom',
        'key': 'start-position',
        'disappear_time': -1
    }]

    for pokemon_key in pokemons:
        pokemon = pokemons[pokemon_key]
        datestr = datetime.fromtimestamp(pokemon[
            'disappear_time'])
        dateoutput = datestr.strftime("%H:%M:%S")
        if is_ampm_clock:
        	dateoutput = datestr.strftime("%I:%M%p").lstrip('0')
        pokemon['disappear_time_formatted'] = dateoutput

        LABEL_TMPL = u'''
<div><b>{name}</b></div>
<div>Disappears at - {disappear_time_formatted} <span class='label-countdown' disappears-at='{disappear_time}'></span></div>
'''
        label = LABEL_TMPL.format(**pokemon)
        #  NOTE: `infobox` field doesn't render multiple line string in frontend
        label = label.replace('\n', '')

        pokeMarkers.append({
            'type': 'pokemon',
            'key': pokemon_key,
            'disappear_time': pokemon['disappear_time'],
            'icon': 'static/icons/%d.png' % pokemon["id"],
            'lat': pokemon["lat"],
            'lng': pokemon["lng"],
            'infobox': label
        })

    for gym_key in gyms:
        gym = gyms[gym_key]
        if gym[0] == 0:
            color = "rgba(0,0,0,.4)"
        if gym[0] == 1:
            color = "rgba(74, 138, 202, .6)"
        if gym[0] == 2:
            color = "rgba(240, 68, 58, .6)"
        if gym[0] == 3:
            color = "rgba(254, 217, 40, .6)"

        icon = 'static/forts/'+numbertoteam[gym[0]]+'_large.png'
        pokeMarkers.append({
            'icon': 'static/forts/' + numbertoteam[gym[0]] + '.png',
            'type': 'gym',
            'key': gym_key,
            'disappear_time': -1,
            'lat': gym[1],
            'lng': gym[2],
            'infobox': "<div><center><small>Gym owned by:</small><br><b style='color:" + color + "'>Team " + numbertoteam[gym[0]] + "</b><br><img id='" + numbertoteam[gym[0]] + "' height='100px' src='"+icon+"'><br>Prestige: " + str(gym[3]) + "</center>"
        })
    for stop_key in pokestops:
        stop = pokestops[stop_key]
        if stop[2] > 0:
            pokeMarkers.append({
                'type': 'lured_stop',
                'key': stop_key,
                'disappear_time': -1,
                'icon': 'static/forts/PstopLured.png',
                'lat': stop[0],
                'lng': stop[1],
                'infobox': 'Lured Pokestop, expires at ' + stop[2],
            })
        else:
            pokeMarkers.append({
                'type': 'stop',
                'key': stop_key,
                'disappear_time': -1,
                'icon': 'static/forts/Pstop.png',
                'lat': stop[0],
                'lng': stop[1],
                'infobox': 'Pokestop',
            })
    return pokeMarkers


if __name__ == '__main__':
    args = get_args()
    app.run(
        debug=True, use_evalex=False, processes=5,
        host=args.host, port=args.port,
    )
