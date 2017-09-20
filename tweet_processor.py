from twitter_handler import twitter_handler
import tweepy
import logging

class tweet_processor(object):
    def __init__(self):
        self.handler = twitter_handler()
        logging.basicConfig(filename="replies.log", level=logging.INFO)

    def get_required_tweets(self,tweet):
        user = tweet.user.screen_name
        tweet_id = tweet.id
        max_id = None
        replies = []
        tweets = self.handler.get_tweets(user,tweet_id,max_id)
        logging.info(tweets)
        try:
            replies.extend(tweets)
        except TypeError:
            replies.append(tweets)
        logging.info("size of replies == %s" % len(replies))
        if len(replies) > 0:
            for reply in replies:
                replies_to_reply = self.get_required_tweets(reply)
                if replies_to_reply is not None:
                    replies.extend(replies_to_reply)
        else:
            return None
        return replies