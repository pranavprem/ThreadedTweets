from tweet_processor import tweet_processor
import tweepy
from os import environ as e

auth = tweepy.AppAuthHandler(e["CONSUMER_KEY"], e["CONSUMER_SECRET"])
api = tweepy.API(auth, wait_on_rate_limit=True,
 				                     wait_on_rate_limit_notify=True)

tp = tweet_processor()
req = tp.get_required_tweets(api.get_status(910002272825831425))
print len(req)
for tweet in req:
    print str(tweet.id) + " ---- " + str(tweet.in_reply_to_status_id)


# from twitter_handler import twitter_handler

# handler = twitter_handler()
# tweet = api.get_status(909950433891827712)
# print tweet.user.screen_name
# print tweet.id
# print len(handler.get_tweets(tweet.user.screen_name,tweet.id,None))