set -xe

server=157.245.101.118

if [ $TRAVIS_BRANCH == 'main' ] ; then
  eval "$(ssh-agent -s)"
  ssh-add ~/.ssh/id_rsa

  rsync -a --exclude={"tests","deploy.sh","travis_rsa.enc","alembic","alembic.ini","isort.cfg"} * travis@$server:/api
  echo "Deployed successfully!"
else
  echo "Not deploying, since the branch isn't main."
fi