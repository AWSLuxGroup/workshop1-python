# web framework-related imports
from flask import Flask, request, redirect, url_for, render_template, g
from datetime import datetime
from werkzeug import secure_filename
import os, sys, logging, uuid
# AWS-related imports
import boto, boto.utils
from boto.s3.key import Key
from boto.dynamodb2.table import Table
from boto.dynamodb2.items import Item
# for thumbnails
from PIL import Image
# App parameters with default values
__default_params = (('BUCKET_SOURCE',   None),
                    ('BUCKET_THUMBS',   None),
                    ('TABLE_ITEMS',     None),
                    ('AWS_REGION',      'eu-west-1'),
                    ('UPLOAD_FOLDER',   '/tmp/'))


#
# initialization
#


application = Flask(__name__)
handler = logging.StreamHandler(sys.stdout)
application.logger.addHandler(handler)
application.logger.setLevel(logging.INFO)
application.logger.info('Application "%s" initialisation', __name__)
# The following parameters are expected to be defined in the environment:
# - BUCKET_SOURCE: S3 bucket containing original media files
# - BUCKET_THUMBS: S3 bucket containing thumbnail files
# - TABLE_ITEMS: DDB table with the list of items
# Apply them to the application config context, and then check if some still have a "None" value. If it's the case, the app will not work. Log the issue and add the info to the global error object.
try: 
    for param in __default_params:
        pname = param[0]
        pvalue = os.getenv(pname)
        if pvalue is None:
            pvalue = param[1]
            if pvalue is None:
                raise KeyError(pname)
        application.config[pname] = pvalue
        application.logger.info('Init: setting "%s"="%s"', pname, pvalue)
except KeyError as kerr:
    application.logger.error('Parameter "%s" not found in environment variables', kerr.message)
    sys.exit(1)
except:
    application.logger.error("Unexpected error: %s" , sys.exc_info())
    raise


#
# AWS clients
#


def get_table():
    """Returns the DynamoDB table object."""
    table = getattr(g, '_table_items', None)
    if table is None:
        ddbclient = boto.dynamodb2.connect_to_region(application.config['AWS_REGION'])
        table = g._table_items = Table(application.config['TABLE_ITEMS'], connection=ddbclient)
    return table


def get_bucket(name):
    """Returns the named bucket."""
    bucket = getattr(g, '_bucket_'+name, None)
    if bucket is None:
        c = boto.connect_s3()
        bucket = c.get_bucket(name, validate=False)
        setattr(g, '_bucket_'+name, bucket)
    return bucket


#
# Request handlers
#


@application.route('/', methods=['GET'])
def route_list():
    """Lists the items."""
    # return render_template('index.html', entries=g.dao.list(), bucket=g.bucket)
    return render_template('list.html',
                           items = get_table().scan(),
                           bsource = application.config['BUCKET_SOURCE'],
                           bthumbs = application.config['BUCKET_THUMBS'])


@application.route('/add', methods=['POST'])
def route_add():
    """File upload route."""
    # UUID for this file
    fid = str(uuid.uuid1())
    # Retreive uploaded file
    rfile = request.files['mediaFile']
    filename = fid + "-" + secure_filename(rfile.filename)
    filepath = os.path.join(application.config['UPLOAD_FOLDER'], filename)
    rfile.save(filepath)
    # Creates a thumbnail
    thumbpath = filepath + ".thumb.jpeg"
    im = Image.open(filepath)
    im.thumbnail((200,200))
    im.save(thumbpath, "JPEG")
    # Uploads the images
    key_thumb = putObject(thumbpath, filename, application.config['BUCKET_THUMBS'])
    key_source = putObject(filepath, filename, application.config['BUCKET_SOURCE'])
    # Adds the entry in DynamoDB
    putRecord(fid, rfile.filename, request.form['caption'], filename, filename)
    # Redisplays the home page
    return redirect(url_for('route_list'))


#
# Helper functions
#


def putObject(filepath, keyname, bucketname):
    """ Uploads a file, composes the keyname based on UUID + filename"""
    k = Key(get_bucket(bucketname))
    k.key = keyname
    k.set_contents_from_filename(filepath)
    return k.key


def putRecord(fid, filename, desc, keysrc, keythb):
    """ Adds a new item to the DynamoDB table."""
    uid = "unique ID"
    timestamp = "timestamp" 
    new_item = Item(get_table(), data={
        'owner': 'Carlos',
        'uid': fid,
        'name': filename,
        'description': desc,
        'timestamp': datetime.today().strftime('%Y%m%d-%H%M%S-%f'),
        'source': keysrc,
        'thumbnail': keythb
    })
    new_item.save()


#
# Start!
#


if __name__ == '__main__':
    application.run(debug=True)
