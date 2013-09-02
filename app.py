import json
import sys
from itertools import product

import pymongo
import networkx
from flask import Flask, render_template, make_response, request, jsonify


app = Flask(__name__)
app.debug = True


@app.route("/graph/")
def home():
    ctx = dict(request.args.items())
    return render_template('index.html', **ctx)


@app.route("/graph/json/<abbr>/<session>/<chamber>/")
def graph_json(abbr, session, chamber):
    data = get_data(abbr, session, chamber)
    return jsonify(data)


class _GraphBuilder(object):
    '''Helper for constructing a cosponsorship graph.
    '''

    def __init__(self, abbr, session, chamber):
        self.db = pymongo.MongoClient().fiftystates
        self.abbr = abbr
        self.session = session
        self.chamber = chamber
        self.G = networkx.DiGraph()
        self.number_of_bills = 0

    def build(self):
        '''Build the graph.
        '''
        spec = {
            'state': self.abbr,
            'chamber': self.chamber,
            'session': self.session}

        for bill in self.db.bills.find(spec).limit(200):
            self.add_bill(bill)
            self.number_of_bills += 1

    def add_bill(self, bill):
        '''Add a single bill to the graph.
        '''
        G = self.G
        sponsors = bill['sponsors']
        if len(sponsors) < 2:
            return

        # Separate sponsors into primary, secondary.
        primary = []
        secondary = []
        for sponsor in sponsors:
            if sponsor['type'] == 'primary':
                primary.append(sponsor['leg_id'])
            else:
                secondary.append(sponsor['leg_id'])

        # Add them to the network.
        if primary and secondary:
            for primary, secondary in product(primary, secondary):
                try:
                    G[secondary][primary]['weight'] += 1
                except KeyError:
                    G.add_edge(secondary, primary, weight=1)

    def pagerank(self):
        return networkx.pagerank(self.G)

    def clusters(self):
        pass


class _JSONGenerator(object):
    '''Helper for generating graph json for d3.
    '''
    def __init__(self, builder):
        self.db = pymongo.MongoClient().fiftystates
        self.builder = builder
        self.pagerank = builder.pagerank()
        self.clusters = builder.clusters()

    def get_legislator_data(self):
        spec = {'_id': {'$in': list(self.pagerank)}}
        fields = ('full_name',)
        return self.db.legislators.find(spec, fields=fields)

    def data(self):
        '''Return the jsonable data expected by the client-side code.
        {
          "nodes":[
            {"name":"Myriel","group":1},
            {"name":"Napoleon","group":1},
          ],
          "links":[
            {"source":0,"target":1,"value":1},
            {"source":1,"target":0,"value":1}
          ]
        }
        '''
        G = self.builder.G
        nodes = G.nodes()
        edges = G.edges()

        data = {}

        # Add pagerank data.
        pagerank = self.pagerank
        leg_data = data['nodes'] = list(self.get_legislator_data())
        for leg in leg_data:
            leg['r'] = pagerank[leg['_id']]

        # Create edge list.
        links = []
        for source, target in edges:
            link = dict(
                source=nodes.index(source),
                target=nodes.index(target),
                value=G[source][target])
            links.append(link)

        data['links'] = links
        return data


def get_data(abbr, session, chamber):
    builder = _GraphBuilder(abbr, session, chamber)
    builder.build()
    return _JSONGenerator(builder).data()


if __name__ == '__main__':
    app.run()
    # data = get_json(*sys.argv[1:])
    # import pdb; pdb.set_trace()

