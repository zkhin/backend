# REAL Backend Integration Testing

The integration tests are written in Javascript for nodejs using the [Jest](https://jestjs.io) testing framework.

Running the integration tests requires a live, deployed copy of this project which will be used to test against.

## Quickstart

- Run `yarn install` in this directory to install needed pacakges.
- Set up a `.env` file with required environment variables
  - Most of the values can be found in the 'Outputs' section of the CloudFormation stack in the AWS console
  - If a required environment variable is not defined, the tests will error out. Hence you can run the tests to discover what values are needed. You will need at least the following variables:
    - `AWS_REGION` (may not be needed, depends on the configuration of your AWS credentials)
    - `AWS_PROFILE` (may not be needed, depends on the configuration of your AWS credentials)
    - `APPSYNC_GRAPHQL_URL`
    - `COGNITO_FRONTEND_CLIENT_ID`
    - `COGNITO_TESTING_CLIENT_ID`
    - `COGNITO_IDENTITY_POOL_ID`
    - `COGNITO_USER_POOL_ID`
    - `DYNAMO_TABLE`
    - `ELASTICSEARCH_ENDPOINT`
    - `PINPOINT_APPLICATION_ID`
    - `S3_UPLOADS_BUCKET`
- Run `yarn test` to run the tests

If the test fail to clean up after themselves, you can use the scripts in the `./clean` directory to help clean up.

There are some scripts meant to be used in an interactive fashion in the `./scripts` directory.
