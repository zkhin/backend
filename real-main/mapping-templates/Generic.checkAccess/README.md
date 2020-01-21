# Generic.checkAccess

Use these pipeline stages to check if a caller should be granted access to a resource. Access will be granted if and only if the resource is
- not owned by a user that has blocked us or we have blocked
- readable by all for public profiles
- readable only by followers for private profiles

The stages here:
- expect that the userId that owns the resource has been set in `$ctx.stash.userId`
- expect `$ctx.stash.accessGranted` has been set to null or left unset
- will overwrite `$ctx.stash.accessGranted` with true/false

The stages may be used in isolation but in general they are expected to be used as a set, in the following order
- Generic.checkAccess.checkIfBlocked
- Generic.checkAccess.checkIfPublic
- Generic.checkAccess.checkIfFollower
