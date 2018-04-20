
import re
import urllib
import datetime
import requests
import svy21

_om = {}
def OneMap(creds):
    global _om
    if creds not in _om:
        _om[creds] = OneMapAPI(creds)
    return _om[creds]

class OneMapAPI(object):

    BASE_DOMAIN = "https://developers.onemap.sg"
    API_ROUTE = ""
    COMMON_PARAMS = {"searchVal": "", "returnGeom": "Y", "getAddrDetails":"Y"}
    WILDCARD_PATTERNS = {
        "startswith": "%s like '%s$'",
        "endswith": "%s like '$%s'",
        "includes": "%s like '$%s$'",
        "plain": "%s like '%s'"
    }
    
    def __init__(self, creds):
        self.creds = creds
        self.token = None
        self.token_expiry = None


    def _ping(self, endpoint, params, api_route=None):
        
        #change url if the method is for token getting
        if params.get('token'):
            url = "%s%s%s" % (self.BASE_DOMAIN, self.API_ROUTE, endpoint)
        else:
            url = "%s%s%s?%s" % (self.BASE_DOMAIN, self.API_ROUTE, endpoint, urllib.urlencode(params))
       
        if not params.get('token'):
            if not self.token:
                self.get_token()
            params['token'] = self.token
        
        print url
        rv = requests.get(url)

        data = {}
        error = None
        page_count = 0
        items = []

        try:
            data = rv.json()
            items;
            if params.get('token'):

                items = rv.json().pop(data.keys()[0])
                
            else:
                
                items = rv.json().pop(data.keys()[2])
                
            
            if items == "[]":
                error = []
                page_count = 0
            elif items == "You are not an authorised user!":
                error = []
                page_count = 0
                items =[]
            elif params.get('token'):
                items = [{"token":items}]

        except ValueError as e:
            error = e

        OMR = OneMapResult(
            endpoint,
            params,
            rv.status_code,
            page_count,
            items,
            error,
            data
        )
        return OMR

    #wildcard function is not valid    
    def _validate_wildcard(self, term, wildcard, search_by=None):
        
        wildcard =  term

        return wildcard


    def _validate_geo(self, with_geo):
        return 1 if with_geo or with_geo is None else 0


    def _validate_page(self, page):
        return 1 if page is None else int(page)


    def _params(self, **kwargs):
        data = self.COMMON_PARAMS.copy()

        if kwargs.get('term') and kwargs.get('wildcard'):
            data['searchVal'] = self._validate_wildcard(kwargs.get('term'), kwargs.get('wildcard'), kwargs.get('search_by'))

        if kwargs.get('with_geo') is not None:
            data['returnGeom'] = self._validate_geo(kwargs.get('with_geo'))

        if kwargs.get('page') is not None:
            data['rset'] = self._validate_page(kwargs.get('page'))

        if kwargs.get('show_fields'):
            data['otptflds'] = kwargs.get('show_fields')

        return data


    def get_token(self):
        
        if self.token and self.token_expire and datetime.datetime.utcnow() < self.token_expiry:
            return self.token

        data = self._ping('/privateapi/auth/get/getToken?'+self.creds, {"token": "Y"})

        if data.raw.get('GetToken') and \
          len(data.raw.get('GetToken')) and \
          data.raw.get('GetToken')[0].get('NewToken'):
            self.token = data.raw.get('GetToken')[0].get('NewToken')
            self.token_expiry = datetime.datetime.utcnow() + datetime.timedelta(hours=72)
            return self.token


    def search_address(self, term, wildcard='startswith', **kwargs):
        
        data = self._ping("/commonapi/search", self._params(term=term, wildcard=wildcard, **kwargs))

        return data


    def geocode(self, location, buffer=100, address_type='all'):
        '''
        Wraps the reverse geocoding API on OneMap

        args
            location          A string in the format "lng,lat", representing the
                              point to reverse geocode

        kwargs
            buffer            Radius around the point within which results should be returned

            address_type      One of 'all' or 'hdb'
                              Returns all location types if 'all' and only HDB results otherwise
        '''

        return self._ping('revgeocode', {
            "location": location,
            "buffer": buffer,
            "addressType": address_type
        })


    def public_transport(self, start, end, walking_distance=100, mode='bus/mrt', route='fastest', with_geo=True, max_solutions=1):
        '''
        Wraps the public transport routing API

        args
            start                   The start point of the route.
                                    Can be an SVY21 coordinate pair, or a Singapore postal code

            end                     The end point of the route
                                    Can be an SVY21 coordinate pair, or a Singapore postal code

        kwargs
            walking_distance        Walking distance to bus or train stop. Defaults to 100

            mode                    String representing preferred mode of transport. Can be
                                    one of "bus" or "bus/mrt"

            route                   One of 'fastest' (default) or 'cheapest'

            with_geo                True, to return segments between start and end points, False otherwise

            max_solutions           Maximum number of solutions to return from the API
        '''

        return self._ping("routesolns", {
            "sl": start,
            "el": end,
            "walkdist": walking_distance,
            "mode": mode,
            "route": route,
            "retgeo": str(with_geo).lower(),
            "maxsolns": max_solutions
        }, api_route="/publictransportation/service1.svc")

    def resolve(self, address, buffer=10):
        m = re.match("(?P<lng>\d+\.\d+),\s?(?P<lat>\d+\.\d+)", address)
        if m:
            x, y = (m.groupdict()['lng'], m.groupdict()['lat'])
        else:
            res = self.search_address(address)
            if res.error:
                raise OneMapError(res.error)
            item = res.items[0]
            x, y = (item.x, item.y)

        geo = self.geocode("%s,%s" % (x, y), buffer=buffer)
        if geo.error:
            raise OneMapError(geo.error)

        item = geo.items[0]
        out = {k: v for k, v in item.iteritems()}
        S = svy21.SVY21()
        i = geo.items[0]
        coordinates = S.computeLatLon(i.y, i.x)
        coordinates = list(coordinates)
        coordinates.reverse()
        out['coordinates'] = coordinates
        return out


class OneMapResult(object):

    def __init__(self, endpoint, params, status_code, page_count, items, error=None, raw=None):
        print items
        self.endpoint = endpoint
        self.params = params
        self.status_code = status_code
        self.page_count = int(page_count) if isinstance(page_count, basestring) else page_count
        self.error = error
        self.raw = raw
        self.items = [OneMapResultItem(**i) for i in items]

    def filter(self, **filters):
        def do_filter(item):
            return all(map(lambda (k,v): (item.get(k) or '').lower() == v.lower(), filters.iteritems()))

        return filter(do_filter, self.items)

    def __getitem__(self, key):
        return self.items[key]

    def __iter__(self):
        return self.items.__iter__()

    def __repr__(self):
        return str(self.items)

    def __str__(self):
        return self.__unicode__()

    def __unicode__(self):
        return str(self.items)


class OneMapResultItem(object):

    def __init__(self, **kwargs):
        self.__raw = {k.lower(): v for k, v in kwargs.items()}

        # Sanitise result field names
        for f in ['xcoord', 'x', 'ycoord', 'y']:
            if self.__raw.get(f):
                self.__raw[f[0]] = float(self.__raw.pop(f))

        if all([self.__raw.get('x'), self.__raw.get('y')]):
            S = svy21.SVY21()
            coordinates = S.computeLatLon(self.__raw['y'], self.__raw['x'])
            self.__raw['lat'] = coordinates[0]
            self.__raw['lng'] = coordinates[1]

    def __getattr__(self, name):
        try:
            return getattr(self.__raw, name)
        except AttributeError:
            if name in self.__raw:
                return self.__raw[name]
            else:
                raise AttributeError()

    def __getitem__(self, name):
        try:
            return self.__raw.get(name)
        except KeyError:
            raise AttributeError()

    def __dir__(self):
        return self.__raw.keys()

    def __repr__(self):
        return str(self.__raw)

    def __str__(self):
        return self.__unicode__()

    def __unicode__(self):
        return unicode(self.__raw)


class OneMapError(Exception):
    pass
