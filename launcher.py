from lib.bot import MOCBOT
import argparse

parser = argparse.ArgumentParser(description='Runs MOCBOT.')
parser.add_argument('--dev', action='store_true', help='Enable development mode.')
args = parser.parse_args()

bot = MOCBOT(args.dev)
bot.run()