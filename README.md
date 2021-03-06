# aether-firebase-cloud-triggers
Collection of Firebase Cloud Triggers for Aether integration

## Concept

This application is a set of cloud functions designed to help keep Firebase data synced to Kafka.

There are conceptual groups of functions, collect and publish. 

![Diagram](/doc/Selection_005.jpg)

## Environment Variables

#### all

You must always indicate the url of the FB instance to be used. Additionally, this FB instance must be in the same GCP project as the cloud functions in order to subscribe to changes on the FB instance.

```
FIREBASE_URL (string) URL of the RTDB instance
```

#### publish

These are required for the entrypoint `run_exporter`

```
KAFKA_URL
KAFKA_SECURITY_PROTOCOL
KAFKA_SASL_MECHANISM
KAFKA_SASL_USERNAME
KAFKA_SASL_PASSWORD
BASE_PATH (string) base path in RTDB instance
SYNC_PATH (string) base path for the SYNC storage structure
    like: /{base_path}{sync_path}/{doc_type}/{documents, schema, options}
TENANT (string) name of the tenant, used to prepend the Kafka topics
    like: {TENANT}.fbs.{doc_type}
```

#### collect

These are required for the entry points:

 - cfs_sync_rtdb
 - cfs_export_rtdb
 - rtdb_sync_rtdb
 - rtdb_export_rtdb

```
SUBSCRIBE_PATTERN (string) the pattern you provided to the firebase cloud function subscription describing the source
    like: /fixed/{variable_a}/{variable_b}
PATH_TEMPLATE (string) the copy destination using (optionally) variables from the subscribe pattern
    like: /new_fixed/some/{variable_a}/path/{variable_b}
    - or -
    /new_fixed/some/path/{variable_b}
```

Keep in mind that in RTDB that there are no lists, only key value pairs, so the last element of the `PATH_TEMPLATE` should in most cases be a variable.


## Operation


The collect functions are cloud functions subscribed through firebase hooks to watch for changes in documents on a path of set of paths in the Cloud Firestore or Realtime Database. The publish function runs on a schedule and publish collected documents to Kafka. There are good reasons not to try to publish from the collect step, which we won't go into in depth here, but they include schema validation, batching of publication for efficient serialization, quarantine of invalid data, and caching for retry in the event that Kafka is unavailable.

The publish function runs on a schedule that you can set. It then batches documents and writes them to Kafka. Only one instance of the exporter should run at a time, and this should be explicitly set in the run rules for the function. The `run_exporter` publish function should be setup to be triggered by GCP pub-sub, whose topic is setup to emit a message on the frequency that you need the exporter to run. The function timeout for the publish function should be at most one minute less than the triggering frequency. I.E. if it must run once every 10 minutes, the timeout should be set at 9 minutes.


![Diagram](/doc/Selection_004.jpg)

Here you see the possible collect functions:
 - cfs_sync_rtdb
 - cfs_export_rtdb
 - rtdb_sync_rtdb
 - rtdb_export_rtdb

The export variants will remove the document from the source store, which is often what you want with RTDB for things like logs as storage there is much more costly than in Kafka. The sync variants do not change the source docs.

You also will note that we create a space for the Exporter in the RTDB. To separate this space from an application that might use the same database, you set a {BASE_PATH} as explained in the environment section. Beyond that, you'll need to specify a schema (as avro stored in JSON), and optionally any supported options for the sync.

