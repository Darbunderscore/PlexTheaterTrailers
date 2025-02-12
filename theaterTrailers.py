#!/usr/bin/python

from __future__ import unicode_literals
from asyncore import ExitNow
from datetime import datetime
from traceback import print_exception
import youtube_dl
import tmdbsimple as tmdb
import logging
import json
import shutil
import re
import os
import time
import requests
import sys

#Local Modules
from ConfigMapper.configMapper import ConfigSectionMap


# Global items
MovieDict = {}
MovieList = []
DirsDict = {}
ResultsDict = {}
search = tmdb.Search()

# Sets the directory TheaterTrailers is running from
TheaterTrailersHome = os.path.dirname(os.path.realpath(__file__))

# Sets the location of the trailers.conf file
if os.path.isfile(os.path.join(TheaterTrailersHome, 'Config', 'trailers.conf')):
  configfile = os.path.join(TheaterTrailersHome, 'Config', 'trailers.conf')
else:
  sys.exit("{0} not found!".format(os.path.join(TheaterTrailersHome, 'Config', 'trailers.conf')))

# Config Variables
tmdb.API_KEY = ConfigSectionMap("main", configfile)['tmdb_api_key']
if tmdb.API_KEY == "replaceMeWithYourApiKey" or tmdb.API_KEY == "":
  sys.exit("TMDB API Key not defined in {0}".format(os.path.join(TheaterTrailersHome, 'Config', 'trailers.conf')))
playlistEndVar = int(ConfigSectionMap("main", configfile)['playlistendvar'])
youtubePlaylist = ConfigSectionMap("main", configfile)['youtubeplaylist']
runCleanup = ConfigSectionMap("main", configfile)['runcleanup']
if ConfigSectionMap("main", configfile)['trailerlocation'] == "":
  trailerLocation = os.path.join(TheaterTrailersHome, 'Trailers')
else:
  trailerLocation = ConfigSectionMap("main", configfile)['trailerlocation']
redBand = ConfigSectionMap("main", configfile)['redband']
plexHost = ConfigSectionMap("main", configfile)['plexhost']
plexPort = ConfigSectionMap("main", configfile)['plexport']
plexToken = ConfigSectionMap("main", configfile)['plextoken']
loggingLevel = ConfigSectionMap("main", configfile)['logginglevel']
radarrHost = ConfigSectionMap("main", configfile)['radarrhost']
radarrPort = ConfigSectionMap("main", configfile)['radarrport']
radarrKey = ConfigSectionMap("main", configfile)['radarrkey']
pushToRadarr = ConfigSectionMap("main", configfile)['pushtoradarr']
pullFromRadarr = ConfigSectionMap("main", configfile)['pullfromradarr']
radarrRootFolderPath = ConfigSectionMap("main", configfile)['radarrrootfolderpath']
radarrURI = ConfigSectionMap("main", configfile)['radarruri']
cacheRefresh = int(ConfigSectionMap("main", configfile)['cacherefresh'])
if not os.path.exists(os.path.join(TheaterTrailersHome, "Cache")):
  os.makedirs(os.path.join(TheaterTrailersHome, "Cache"))
cacheDir = os.path.join(TheaterTrailersHome, "Cache")


# Pause in seconds. TMDB has a rate limit of 40 requests per 10 seconds
pauseRate = .25

# Logging options
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
if not os.path.isdir(os.path.join(TheaterTrailersHome, 'Logs')):
  os.makedirs(os.path.join(TheaterTrailersHome, 'Logs'))
if os.path.isfile(os.path.join(TheaterTrailersHome, 'theaterTrailers.log')):
  shutil.move(os.path.join(TheaterTrailersHome, 'theaterTrailers.log'), os.path.join(TheaterTrailersHome, 'Logs', 'theaterTrailers.log'))
fh = logging.FileHandler(os.path.join(TheaterTrailersHome, 'Logs', 'theaterTrailers.log'))
fh.setLevel(logging.INFO)
fh.setFormatter(formatter)
logger.addHandler(fh)
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
ch.setFormatter(formatter)
logger.addHandler(ch)

# Sets the Current Date in ISO format
currentDate = time.strftime('%Y-%m-%d')


# Main detirmines the flow of the module
def main():

  if runCleanup == 'True':
    cleanup()

  checkCashe()

  infoDownloader(youtubePlaylist)

  # Querries tmdb and updates the release date in the dictionary
  for item in MovieList:
    try:
      if MovieDict['item']['Release Date'] in MovieDict:
        continue
    except KeyError as ke1:
      with open(os.path.join(cacheDir, 'theaterTrailersCache.json'), 'r') as fp:
        try:
          DB_Dict = json.load(fp)
          MovieDict[item]['Release Date'] = DB_Dict[keymaker(item)]['Release Date']

        except (KeyError, ValueError) as e:
          tmdbInfo(item)
          tempList = search.results
          tempList.reverse()
          for s in tempList:
            releaseDate = s.get('release_date', '1900-01-01')
            movieTMDBID = s['id']
            releaseDateList = releaseDate.split('-')
            try:
              if (int(releaseDateList[0]) - 1) <= int(MovieDict[item]['Trailer Release']) <= (int(releaseDateList[0]) + 1):
                MovieDict[item]['Release Date'] = releaseDate
                MovieDict[item]['TMDB ID'] = movieTMDBID
            except ValueError as e:
              logger.error("ValueError for {0} {1} 119".format(item, e))
              pass
            except KeyError as e:
              logger.error("KeyError for {0} {1} 122".format(item, e))
              try:
                MovieDict[item]['Release Date'] = releaseDate
                MovieDict[item]['TMDB ID'] = movieTMDBID
              except ValueError as e:
                logger.error("ValueError {0} 127".format(e))
                pass

        except AttributeError as ae1:
          logger.error("AttributeError {0} 131".format(item))
          continue

    # Adds the movies to the cache
    title = item.strip()
    try:
      yearVar = MovieDict[item]['Release Date'].split('-')
      trailerYear = yearVar[0].strip()
      updateCache(MovieDict[item]['url'], title, trailerYear)
    except KeyError as error:
      logger.warning("{0} is missing its release date".format(item))


def addToRadarr(movieTitle, yearVar, tmdbMovieKey, radarrRootFolderPath):
  if radarrKey == "" or radarrHost == "" or radarrPort == "":
    return
  elif pushToRadarr == False:
    return
  else:
    headers = {
     'X-Api-Key': radarrKey
    }
    r = requests.post('http://{0}:{1}/{2}/api/movie/'.format(radarrHost, radarrPort, radarrURI), headers=headers, json={
      "title": "{0} ({1})".format(movieTitle, yearVar),
      "profileId": 6,
      "titleSlug": "{0}-{1}".format(slugger(movieTitle), tmdbMovieKey),
      "images": [],
      "tmdbId": "{0}".format(tmdbMovieKey),
      "rootFolderPath": "{0}".format(radarrRootFolderPath)
    })



def checkCashe():
    logger.info("Checking cache...")
    if os.path.exists(cacheDir):
      if os.path.isfile(os.path.join(cacheDir, 'theaterTrailersCache.json')):
        with open(os.path.join(cacheDir, 'theaterTrailersCache.json')) as fp:
          try:
            cacheDict = json.load(fp)
            creationDate = datetime.strptime(cacheDict['Creation Date'] , '%Y-%m-%d').date()
            Current_Date = datetime.strptime(currentDate, '%Y-%m-%d').date()
            age = Current_Date - creationDate
            age = age.days
            logger.info('The cache is {0} days old'.format(age))
            if (age >= cacheRefresh):
              logger.info('The cache will be refreshed')
              os.remove(os.path.join(cacheDir, 'theaterTrailersCache.json'))
              open(os.path.join(cacheDir, 'theaterTrailersCache.json'), 'w').close()
            else:  
              attrib_set = ['url', 'Trailer Release', 'Movie Title', 'Release Date', 'TMDB ID', 'path', 'status' ]                                          
              for item in cacheDict:
                if item == 'Creation Date':
                  continue
                attribs = (list(cacheDict[item].keys()))
                for attrib in attrib_set:
                  if attrib not in attribs:
                    logger.warning('Cache is corrupt.')
                    fp.close() 
                    try:
                      os.remove(os.path.join(cacheDir, 'theaterTrailersCache.json'))
                    except OSError as e:
                      logger.info('OSError {0}'.format(e))
                    open(os.path.join(cacheDir, 'theaterTrailersCache.json'), 'w').close()
                    return       
                    
          except ValueError as e:
            logger.info("ValueError {0}".format(e))
            logger.info("Cache file empty")
      
      else:
        logger.info("Cache file not found. Creating...")
        open(os.path.join(cacheDir, 'theaterTrailersCache.json'), 'w').close()
    
    else:
      logger.info("Creating cache directory and file...")
      os.makedirs(cacheDir)
      open(os.path.join(cacheDir, 'theaterTrailersCache.json'), 'w').close()

def checkDownloadDate(passedTitle):
  try:
    if currentDate < MovieDict[passedTitle]['Release Date']:
      return True
  except KeyError as ke2:
    logger.error("KeyError {0} 192".format(ke2))
    logger.error(MovieDict[passedTitle] + " has no release date")

def keymaker(string):
  chars_to_remove = [" ", "?", ".", "!", "/", ":", ";", "'", "-", ","]
  sc = set(chars_to_remove)
  string = string.lower()
  string = ''.join([c for c in string if c not in sc])
  return string

def slugger(string):
  string = string.replace(" ", "-")
  chars_to_remove = ["?", ".", "!", "/", ":", ";", "'", ","]
  sc = set(chars_to_remove)
  string = string.lower()
  string = ''.join([c for c in string if c not in sc])
  return string

def updateCache(string, passedTitle, yearVar):
  passedSmallTitle = keymaker(passedTitle)
  with open(os.path.join(cacheDir, 'theaterTrailersCache.json'), 'r') as fp:
    try:
      jsonDict = json.load(fp)
      try:
        if jsonDict[passedSmallTitle]['url'] == string:
          if jsonDict[passedSmallTitle]['status'] == 'Downloaded':
            if checkFiles(passedTitle, yearVar):
              logger.info('{0} from {1} is already downloaded'.format(passedTitle, string))
              return
            else:
              logger.info('{0} from {1} was in the cache but did not exist'.format(passedTitle, string))
              if yearVar == MovieDict[passedTitle]['Trailer Year']:
                videoDownloader(string,passedTitle,yearVar)
              else:
                with open(os.path.join(cacheDir, 'theaterTrailersTempCache.json'), 'w') as temp1:
                  jsonDict[passedSmallTitle]['Trailer Year'] = MovieDict[passedTitle]['Trailer Year']
                  videoDownloader(string,passedTitle,MovieDict[passedTitle]['Trailer Year'])
                  json.dump(jsonDict, temp1, indent=4)
          elif jsonDict[passedSmallTitle]['status'] == 'Released':
            logger.info('{0} from {1} has been released'.format(passedTitle, string))
            return
          else:
            logger.error('error with {0} from {1}'.format(passedTitle, string))
        else:
          logger.info('New trailer for {0}'.format(passedTitle))
          with open(os.path.join(cacheDir, 'theaterTrailersTempCache.json'), 'w') as temp2:
            jsonDict[passedSmallTitle]['url'] = string
            if checkDownloadDate(passedTitle):
              shutil.rmtree(jsonDict[passedSmallTitle]['path'])
              videoDownloader(string, jsonDict[passedSmallTitle]['Movie Title'], yearVar)
              jsonDict[passedSmallTitle]['status'] = 'Downloaded'
            else:
              jsonDict[passedSmallTitle]['status'] = 'Released'
            json.dump(jsonDict, temp2, indent=4)

      except KeyError as e:
        logger.info('Creating New Entry')
        with open(os.path.join(cacheDir, 'theaterTrailersTempCache.json'), 'w') as temp3:
          jsonDict[passedSmallTitle] = MovieDict[passedTitle]
          jsonDict[passedSmallTitle]['path'] = os.path.join(trailerLocation, '{0} ({1})'.format(passedTitle, yearVar))
          if checkDownloadDate(passedTitle):
            videoDownloader(string,passedTitle,yearVar)
            jsonDict[passedSmallTitle]['status'] = 'Downloaded'
          else:
            jsonDict[passedSmallTitle]['status'] = 'Released'
          json.dump(jsonDict, temp3, indent=4)
          addToRadarr(passedTitle, yearVar, jsonDict[passedSmallTitle]['TMDB ID'], radarrRootFolderPath)

    except ValueError as e:
      logger.info('Creating Cache')
      jsonDict = {}
      jsonDict['Creation Date'] = currentDate
      jsonDict[passedSmallTitle] = MovieDict[passedTitle]
      jsonDict[passedSmallTitle]['path'] = os.path.join(trailerLocation, '{0} ({1})'.format(passedTitle, yearVar))
      with open(os.path.join(cacheDir, 'theaterTrailersTempCache.json'), 'w') as temp4:
        if checkDownloadDate(passedTitle):
          videoDownloader(string, passedTitle, yearVar)
          jsonDict[passedSmallTitle]['status'] = 'Downloaded'
        else:
          jsonDict[passedSmallTitle]['status'] = 'Released'
          json.dump(jsonDict, temp4, indent=4)
      addToRadarr(passedTitle, yearVar, jsonDict[passedSmallTitle]['TMDB ID'], radarrRootFolderPath)


  if os.path.isfile(os.path.join(cacheDir, 'theaterTrailersTempCache.json')):
    shutil.move(os.path.join(cacheDir, 'theaterTrailersTempCache.json'), os.path.join(cacheDir, 'theaterTrailersCache.json'))


# Downloads the video, names it and copies the resources to the folder
def videoDownloader(string, passedTitle, yearVar):
  # Options for the video downloader
  ydl1_opts = {
    'outtmpl': os.path.join(trailerLocation, '{0} ({1})'.format(passedTitle, yearVar), '{0} ({1}).mp4'.format(passedTitle, yearVar)),
    'ignoreerrors': True,
    'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
  }
  with youtube_dl.YoutubeDL(ydl1_opts) as ydl:
    logger.info("downloading {0} from {1}...".format(passedTitle, string))
    try:
      ydl.cache.remove()
      ydl.download([string])
    except youtube_dl.DownloadError as error:
      return
    time.sleep(3)  
  
  os.chmod(os.path.join(trailerLocation, '{0} ({1})'.format(passedTitle, yearVar), '{0} ({1}).mp4'.format(passedTitle, yearVar)), 0o777)
  try:
    shutil.copy2(
        os.path.join(trailerLocation, '{0} ({1})'.format(passedTitle, yearVar), '{0} ({1}).mp4'.format(passedTitle, yearVar)),
        os.path.join(trailerLocation, '{0} ({1})'.format(passedTitle, yearVar), '{0} ({1})-trailer.mp4'.format(passedTitle, yearVar))
      )
    shutil.copy2(
        os.path.join(TheaterTrailersHome, 'res', 'poster.jpg'),
        os.path.join(trailerLocation, '{0} ({1})'.format(passedTitle, yearVar))
      )
    os.chmod(os.path.join(trailerLocation, '{0} ({1})'.format(passedTitle, yearVar), 'poster.jpg'), 0o777)
  except OSError as e:
    logger.error('OSERROR: {0}'.format(e))
    logger.info('INFO: Skipping {0}'.format(passedTitle))
    return
  updatePlex()


# Downloads info for the videos from the playlist
def infoDownloader(playlist):
  # Options for the info downloader
  logger.info("Downloading movie info...")
  ydl_opts = {
    'skip_download': True,
    'ignoreerrors': True,
    'playlistreverse': True,
    'playliststart': 1,
    'playlistend': playlistEndVar,
    'quiet': False,
    'matchtitle': '.*\\btrailer\\b.*',
    'extract_flat': True,
  }
  with youtube_dl.YoutubeDL(ydl_opts) as ydl:
    info = ydl.extract_info(playlist)

  for x in info['entries']:
    MovieVar = x['title']
    MovieVar = MovieVar.replace(':', '')
    if 'Official' in MovieVar:
      regexedTitle = re.search('^.*(?=(Official))', MovieVar)
    elif 'Trailer' in MovieVar:
      regexedTitle = re.search('.*?(?=Trailer)', MovieVar)
    elif redBand == True:
      if 'Red Band' in MovieVar:
        regexedTitle = re.search('.*?(?=Red)', MovieVar)
    else:
      # Throws out edge cases
      continue
    trailerYear = re.search('(?<=\().*(?=\))', MovieVar)
    TempDict = { 'url' : info['entries'][info['entries'].index(x)]['url']}
    movieTitleUntrimmed = regexedTitle.group(0).strip()
    movieTitle = fixTitle(movieTitleUntrimmed)
    MovieDict[movieTitle] = TempDict
    try:
      MovieDict[movieTitle]['Trailer Release'] = trailerYear.group(0)
    except AttributeError:
      pass
    MovieDict[movieTitle]['Movie Title'] = movieTitle
    MovieList.append(movieTitle)

def fixTitle(movieTitle):
  if "Red Band" in movieTitle:
    movieTitle = ' '.join(movieTitle.split(' ')[:-2])
  stopwords = ['Teaser','teaser']
  querywords = movieTitle.split()
  resultwords  = [word for word in querywords if word.lower() not in stopwords]
  result = ' '.join(resultwords)
  return result

def updatePlex():
  if plexHost == "" or plexPort == "" or plexToken == "":
    return
  else:
    r = requests.get('http://{0}:{1}/library/sections/1/refresh?X-Plex-Token={2}'.format(plexHost, plexPort, plexToken))
    if r.status_code != 200:
      logger.warning("The plex server at {0}:{1} did not respond correctly to the request".format(plexHost, plexPort))

# Returns results from tmdb
def tmdbInfo(item):
  response = search.movie(query=item)
  logger.info("querying the movie db for {0}".format(item))
  time.sleep(pauseRate)
  return search.results


def checkFiles(title, year):
  if os.path.isfile(os.path.join(trailerLocation, '{0} ({1})'.format(title, year), '{0} ({1}).mp4'.format(title, year))):
    if not os.path.isfile(os.path.join(trailerLocation, '{0} ({1})'.format(title, year), '{0} ({1})-trailer.mp4'.format(title, year))):
      shutil.copy2(
        os.path.join(trailerLocation, '{0} ({1})'.format(title, year), '{0} ({1}).mp4'.format(title, year)),
        os.path.join(trailerLocation, '{0} ({1})'.format(title, year), '{0} ({1})-trailer.mp4'.format(title, year))
      )
      updatePlex()
    if not os.path.isfile(os.path.join(trailerLocation, '{0} ({1})'.format(title, year), 'poster.jpg')):
      shutil.copy2(
        os.path.join(TheaterTrailersHome, 'res', 'poster.jpg'),
        os.path.join(trailerLocation, '{0} ({1})'.format(title, year))
      )
      os.chmod(os.path.join(trailerLocation, '{0} ({1})'.format(title, year), 'poster.jpg'), 0o777)
      updatePlex()
    return True
  if os.path.isfile(os.path.join(trailerLocation, '{0} ({1})'.format(title, year), '{0} ({1})-trailer.mp4'.format(title, year))):
    if not os.path.isfile(os.path.join(trailerLocation, '{0} ({1})'.format(title, year), '{0} ({1}).mp4'.format(title, year))):
      shutil.copy2(
        os.path.join(trailerLocation, '{0} ({1})'.format(title, year), '{0} ({1})-trailer.mp4'.format(title, year)),
        os.path.join(trailerLocation, '{0} ({1})'.format(title, year), '{0} ({1}).mp4'.format(title, year))
      )
      updatePlex()
    if not os.path.isfile(os.path.join(trailerLocation, '{0} ({1})'.format(title, year), 'poster.jpg')):
      shutil.copy2(
        os.path.join(TheaterTrailersHome, 'res', 'poster.jpg'),
        os.path.join(trailerLocation, '{0} ({1})'.format(title, year))
      )
      os.chmod(os.path.join(trailerLocation, '{0} ({1})'.format(title, year), 'poster.jpg'), 0o777)
      updatePlex()
    return True
  else:
    return False


# Gets a list of the movies in the directory and removes old movies
def cleanup():
  logger.info("Running cleanup....")
  if not os.path.isdir(os.path.join(TheaterTrailersHome, trailerLocation)):
    logger.warning("Trailer directory not found.")
    return
  else:
    if os.path.isfile(os.path.join(TheaterTrailersHome, trailerLocation, '.DS_Store')):
      os.remove(os.path.join(TheaterTrailersHome, trailerLocation, '.DS_Store'))
    dirsList = os.listdir(os.path.join(TheaterTrailersHome, trailerLocation))
    for item in dirsList:
      dirsTitle = re.search('^.*(?=(\())', item)
      dirsTitle = dirsTitle.group(0).strip()
      dirsYear = re.search('(?<=\().*(?=\))', item)
      dirsYear = dirsYear.group(0).strip()
      filePath = os.path.join(cacheDir, 'theaterTrailersCache.json')
      if (os.path.isfile(filePath)):
        with open(filePath, 'r') as fp:
          try:
            data = json.load(fp)
            releaseDate = data[keymaker(dirsTitle)]['Release Date']
            logger.info("Movie: {0} Release Date: {1}".format(dirsTitle,releaseDate))
            if releaseDate <= currentDate:
              logger.info("Removing {0}. Release date has passed.".format(dirsTitle))
              shutil.rmtree(os.path.join(TheaterTrailersHome, trailerLocation, '{0} ({1})'.format(dirsTitle, dirsYear)))
              updatePlex()
          except KeyError as ex:
            logger.info(ex)
            logger.info("Removing {0}. Release date has passed.".format(dirsTitle))
            shutil.rmtree(os.path.join(TheaterTrailersHome, trailerLocation, '{0} ({1})'.format(dirsTitle, dirsYear)))
            updatePlex()
          except ValueError as Ve:
            logger.warning("Value Error {0}".format(Ve))
            noCacheCleanup(dirsTitle, dirsYear)

def noCacheCleanup(dirsTitle, dirsYear):
  s = tmdbInfo(dirsTitle)
  for s in search.results:
    releaseDate = s.get('release_date', '1900-01-01')
    releaseDateList = releaseDate.split('-')
    if dirsYear >= releaseDateList[0]:
      if releaseDate <= currentDate:
        logger.info("Removing {0}. Release date has passed.".format(dirsTitle))
        shutil.rmtree(os.path.join(TheaterTrailersHome, trailerLocation, '{0} ({1})'.format(dirsTitle, dirsYear)))
        updatePlex()
        break


if __name__ == "__main__":
  main()
