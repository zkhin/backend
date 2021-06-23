module.exports.cognitoIdentityPoolAuthRolePolicyStatements = () => {
  // 'GraphQlApi' name comes from https://github.com/sid88in/serverless-appsync-plugin/blob/1.1.1/index.js#L11
  const AWS_IDS = process.env.COGNITO_AUTH_ROLE_EXECUTE_API_AWS_ACCOUNT_IDS
  return [
    {
      Effect: 'Allow',
      Action: 'appsync:GraphQL',
      Resource: {
        'Fn::Join': [
          '/',
          ['arn:aws:appsync:#{AWS::Region}:#{AWS::AccountId}:apis', {'Fn::GetAtt': ['GraphQlApi', 'ApiId']}, '*'],
        ],
      },
    },
    {
      Effect: 'Allow',
      Action: 'mobiletargeting:PutEvents',
      Resource: {'Fn::Join': ['/', [{'Fn::GetAtt': ['PinpointApp', 'Arn']}, 'events']]},
    },
    ...[
      {
        Effect: 'Allow',
        Action: 'execute-api:Invoke',
        Resource: (AWS_IDS || '')
          .split(' ')
          .filter(Boolean)
          .map((aid) => `arn:aws:execute-api:*:${aid}:*/*/*/*`),
      },
    ].filter(({Resource}) => Resource.length > 0),
  ]
}
