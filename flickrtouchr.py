#!/usr/bin/env python

#
# FlickrTouchr - a simple python script to grab all your photos from flickr, 
#                dump into a directory - organised into folders by set - 
#                along with any favourites you have saved.
#
#                You can then sync the photos to an iPod touch.
#
# Version:       1.2
#
# Original Author:	colm - AT - allcosts.net  - Colm MacCarthaigh - 2008-01-21
#
# Modified by:			Dan Benjamin - http://hivelogic.com										
#
# License:       		Apache 2.0 - http://www.apache.org/licenses/LICENSE-2.0.html
#

from optparse import OptionParser
import cPickle
import hashlib
import hashlib
import os
import sys
import traceback
import unicodedata
import urllib2
import urlparse
import webbrowser
import xml.dom.minidom

API_KEY       = "e224418b91b4af4e8cdb0564716fa9bd"
SHARED_SECRET = "7cddb9c9716501a0"
ALL_PHOTOS = 'all_photos'

#
# Utility functions for dealing with flickr authentication
#
def getText(nodelist):
    rc = ""
    for node in nodelist:
        if node.nodeType == node.TEXT_NODE:
            rc = rc + node.data
    return rc.encode("utf-8")

def getString(dom, tag):
    str = getText(dom.getElementsByTagName(tag)[0].childNodes)
    # Normalize to ASCII
    str = unicodedata.normalize('NFKD', str.decode("utf-8", "ignore")).encode('ASCII', 'ignore')
    return str

def getTitle(dom):
    return getString(dom, "title")

#
# Get the frob based on our API_KEY and shared secret
#
def getfrob():
    # Create our signing string
    string = SHARED_SECRET + "api_key" + API_KEY + "methodflickr.auth.getFrob"
    hash   = hashlib.md5(string).hexdigest()

    # Formulate the request
    url    = "https://api.flickr.com/services/rest/?method=flickr.auth.getFrob"
    url   += "&api_key=" + API_KEY + "&api_sig=" + hash

    try:
        # Make the request and extract the frob
        response = urllib2.urlopen(url)
    
        # Parse the XML
        dom = xml.dom.minidom.parse(response)

        # get the frob
        frob = getText(dom.getElementsByTagName("frob")[0].childNodes)

        # Free the DOM 
        dom.unlink()

        # Return the frob
        return frob

    except:
        raise "Could not retrieve frob"

#
# Login and get a token
#
def froblogin(frob, perms):
    string = SHARED_SECRET + "api_key" + API_KEY + "frob" + frob + "perms" + perms
    hash   = hashlib.md5(string).hexdigest()

    # Formulate the request
    url    = "https://api.flickr.com/services/auth/?"
    url   += "api_key=" + API_KEY + "&perms=" + perms
    url   += "&frob=" + frob + "&api_sig=" + hash

    # Tell the user what's happening
    print "In order to allow FlickrTouchr to read your photos and favourites"
    print "you need to allow the application. Please press return when you've"
    print "granted access at the following url (which should have opened"
    print "automatically)."
    print
    print url
    print 
    print "Waiting for you to press return"

    # We now have a login url, open it in a web-browser
    webbrowser.open_new(url)

    # Wait for input
    sys.stdin.readline()

    # Now, try and retrieve a token
    string = SHARED_SECRET + "api_key" + API_KEY + "frob" + frob + "methodflickr.auth.getToken"
    hash   = hashlib.md5(string).hexdigest()
    
    # Formulate the request
    url    = "https://api.flickr.com/services/rest/?method=flickr.auth.getToken"
    url   += "&api_key=" + API_KEY + "&frob=" + frob
    url   += "&api_sig=" + hash

    # See if we get a token
    try:
        # Make the request and extract the frob
        response = urllib2.urlopen(url)
    
        # Parse the XML
        dom = xml.dom.minidom.parse(response)

        # get the token and user-id
        token = getText(dom.getElementsByTagName("token")[0].childNodes)
        nsid  = dom.getElementsByTagName("user")[0].getAttribute("nsid")

        # Free the DOM
        dom.unlink()

        # Return the token and userid
        return (nsid, token)
    except:
        raise "Login failed"

# 
# Sign an arbitrary flickr request with a token
# 
def flickrsign(url, token):
    query  = urlparse.urlparse(url).query
    query += "&api_key=" + API_KEY + "&auth_token=" + token
    params = query.split('&') 

    # Create the string to hash
    string = SHARED_SECRET
    
    # Sort the arguments alphabettically
    params.sort()
    for param in params:
        string += param.replace('=', '')
    hash   = hashlib.md5(string).hexdigest()

    # Now, append the api_key, and the api_sig args
    url += "&api_key=" + API_KEY + "&auth_token=" + token + "&api_sig=" + hash
    
    # Return the signed url
    return url

#
# Grab the photo from the server
#
def getphoto(id, token, filename):
    try:
        # Contruct a request to find the sizes
        url  = "https://api.flickr.com/services/rest/?method=flickr.photos.getSizes"
        url += "&photo_id=" + id

        # Sign the request
        url = flickrsign(url, token)

        # Make the request
        response = urllib2.urlopen(url)

        # Parse the XML
        dom = xml.dom.minidom.parse(response)

        # Get the list of sizes
        sizes =  dom.getElementsByTagName("size")

        # Grab the original if it exists
        allowedTags = ["Original", "Large", "Large 2048", "Video Original"]
        largestLabel = sizes[-1].getAttribute("label")
        #print "%s" % [i.getAttribute("label") for i in sizes]
        if (largestLabel in allowedTags):
            imgurl = sizes[-1].getAttribute("source")
        else:
            print "Failed to get %s for photo id %s" % (largestLabel, id)

        # Free the DOM memory
        dom.unlink()

        # Grab the image file
        response = urllib2.urlopen(imgurl)
        data = response.read()

        if os.access(filename, os.R_OK):
            flickr_sum = hashlib.md5(data).hexdigest()
            file_sum = hashlib.md5(open(filename, 'rb').read()).hexdigest()
            if flickr_sum == file_sum:
                print 'refreshing timestamp for %s' % filename
                os.utime(filename, None)
                return

        # Save the file!
        if not os.path.isdir(ALL_PHOTOS):
            os.makedirs(ALL_PHOTOS)

        print "saving photo %s" % filename
        fh = open(filename, "w")
        fh.write(data)
        fh.close()

    except urllib2.URLError, err:
        print "error downloading %s" % err.reason

def getUser():
    # First things first, see if we have a cached user and auth-token
    try:
        cache = open("touchr.frob.cache", "r")
        config = cPickle.load(cache)
        cache.close()

    # We don't - get a new one
    except:
        (user, token) = froblogin(getfrob(), "read")
        config = { "version":1 , "user":user, "token":token }  

        # Save it for future use
        cache = open("touchr.frob.cache", "w")
        cPickle.dump(config, cache)
        cache.close()
    return config

def setUrls(setId, urls, config):
    url = "https://api.flickr.com/services/rest/?method=flickr.photosets.getInfo"
    url += "&photoset_id=" + setId
    url = flickrsign(url, config["token"])

    try:
        response = urllib2.urlopen(url)
    except:
        exit(1)
    dom = xml.dom.minidom.parse(response)
    sets =  dom.getElementsByTagName("photoset")

    # For each set - create a url
    for set in sets:
        dir = formatSetDir(set)

        # Build the list of photos
        url   = "https://api.flickr.com/services/rest/?method=flickr.photosets.getPhotos"
        url  += "&extras=original_format,media,last_update"
        url  += "&photoset_id=" + setId

        # Append to our list of urls
        urls.append( (url , dir) )
    
    return urls

def userUrls(userId, tags, urls, config):
    url = "https://api.flickr.com/services/rest/?method=flickr.people.getInfo"
    url += "&user_id=" + userId
    url = flickrsign(url, config["token"])

    response = urllib2.urlopen(url)
    dom = xml.dom.minidom.parse(response)
    person =  dom.getElementsByTagName("person")[0]
    username = getString(person, "username")

    if not tags:
        # Build the list of photos
        url   = "https://api.flickr.com/services/rest/?method=flickr.favorites.getList"
        url  += "&user_id=" + userId
        url  += "&extras=last_update"
    else:
        url   = "https://api.flickr.com/services/rest/?method=flickr.photos.search"
        url  += "&user_id=" + userId
        url  += "&tags=" + tags
        url  += "&extras=last_update"

    # Append to our list of urls
    urls.append( (url , '%s - %s' % (username, tags)) )
    return urls


def formatSetDir(set):
    pid = set.getAttribute("id")
    return '%s - %s' % (getTitle(set), pid)


def allUrls(urls, printSets, config):
    # Now, construct a query for the list of photo sets
    url  = "https://api.flickr.com/services/rest/?method=flickr.photosets.getList"
    url += "&user_id=" + config["user"]
    url  = flickrsign(url, config["token"])

    # get the result
    response = urllib2.urlopen(url)
    
    # Parse the XML
    dom = xml.dom.minidom.parse(response)

    # Get the list of Sets
    sets =  dom.getElementsByTagName("photoset")

    # For each set - create a url
    for set in sets:
        pid = set.getAttribute("id")
        dir = formatSetDir(set)

        # Build the list of photos
        url   = "https://api.flickr.com/services/rest/?method=flickr.photosets.getPhotos"
        url  += "&extras=original_format,media,last_update"
        url  += "&photoset_id=" + pid

        if printSets:
            print pid, dir
            print url

        # Append to our list of urls
        urls.append( (url , dir) )
    
    # Free the DOM memory
    dom.unlink()

    urls.reverse()

    # Add the photos which are not in any set
    url   = "https://api.flickr.com/services/rest/?method=flickr.photos.getNotInSet"
    url  += "&extras=original_format,media,last_update"
    urls.append( (url, None) )

    # Add the user's Favourites
    url   = "https://api.flickr.com/services/rest/?method=flickr.favorites.getList"
    url  += "&extras=original_format,media,last_update"
    urls.append( (url, "favorites from others") )
    
    return urls

def getNewPhotos(urls, config):
    # Time to get the photos
    inodes = {}
    newFiles = []
    maybeUpdatedFiles = []
    for (url , dir) in urls:
        # Create the directory
        try:
            os.makedirs(dir)
        except:
            pass

        # Get 500 results per page
        url += "&per_page=500"
        pages = page = 1

        while page <= pages: 
            request = url + "&page=" + str(page)

            # Sign the url
            request = flickrsign(request, config["token"])

            # Make the request
            response = urllib2.urlopen(request)

            # Parse the XML
            dom = xml.dom.minidom.parse(response)

            # Get the total
            try:
                pages = int(dom.getElementsByTagName("photo")[0].parentNode.getAttribute("pages"))
            except IndexError:
                pages = 0

            # Grab the photos
            for photo in dom.getElementsByTagName("photo"):
                # Tell the user we're grabbing the file

                # Grab the id
                photoid = photo.getAttribute("id")
                media = photo.getAttribute("media")
                last_update = int(photo.getAttribute("lastupdate"))
                if media == "video":
                    extension = ".mov"
                else:
                    extension = ".jpg"

                # The target
                target = ALL_PHOTOS + "/" + photoid + extension
                set_target = dir + "/" + photoid + extension if dir else None
                dirName = dir if dir else ""

                # Record files that exist
                if os.access(target, os.R_OK):
                    inodes[photoid] = target
                    maybeLink(target, set_target)

                    mtime = os.path.getmtime(target)
                    if last_update > int(mtime):
                        maybeUpdatedFiles.append((photo, target, set_target))
                        print photoid + " ... maybe updated in set ... " + dirName
                else:
                    newFiles.append((photo, target, set_target))
                    print photoid + " ... in set ... " + dirName

            # Move on the next page
            page = page + 1


    downloadPhotos(maybeUpdatedFiles, inodes, config)
    downloadPhotos(newFiles, inodes, config)

def maybeLink(target, set_target):
    if set_target and not os.access(set_target, os.R_OK):
       print "linking photo %s to %s" % (target, set_target)
       os.link(target, set_target)

def downloadPhotos(newFiles, inodes, config):
    for (photo, target, set_target) in newFiles:
        photoid = photo.getAttribute("id")
        getphoto(photo.getAttribute("id"), config["token"], target)
        inodes[photoid] = target
        maybeLink(target, set_target)

######## Main Application ##########
def main():
    # The first, and only argument needs to be a directory

    parser = OptionParser()
    parser.add_option("-s", "--setid", dest="setid",
            help="optional specific set to download")
    parser.add_option("-u", "--userid", dest="userid",
            help="optional specific user's favorites or tags to download")
    parser.add_option("-t", "--tags", dest="tags",
            help="optional specific user's tags to download")
    parser.add_option("-d", "--destination", dest="destination",
            help="directory to save backup")
    parser.add_option("-p", "--print-sets", dest="printSets", action="store_true", default=False,
            help="only print set info")
    (options, args) = parser.parse_args()

    setId = None
    userId = None
    tags = None
    printSets = options.printSets
    try:
        destination = options.destination
        setId = options.setid
        userId = options.userid
        tags = options.tags
        os.chdir(destination)
    except Exception, e:
        print type(e).__name__, e
        print "usage: %s directory" % sys.argv[0] 
        sys.exit(1)

    try:
        config = getUser()

        urls = []

        if setId:
            urls = setUrls(setId, urls, config)

        elif userId:
            urls = userUrls(userId, tags, urls, config)

        else:
            urls = allUrls(urls, printSets, config)

        if printSets:
            exit(1)

        getNewPhotos(urls, config)

    except Exception, e:
        print traceback.format_exc()
        print type(e).__name__, e

if __name__ == '__main__':
   try:
      main()
   except urllib2.URLError:
      pass
