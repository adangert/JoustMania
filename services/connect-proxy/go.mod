module github.com/joustmania/connect-proxy

go 1.22

require (
	connectrpc.com/connect v1.17.0
	github.com/rs/cors v1.11.0
	google.golang.org/grpc v1.67.1
	google.golang.org/protobuf v1.35.1
)

require (
	golang.org/x/net v0.29.0 // indirect
	golang.org/x/sys v0.25.0 // indirect
	golang.org/x/text v0.18.0 // indirect
	google.golang.org/genproto/googleapis/rpc v0.0.0-20240814211410-ddb44dafa142 // indirect
)

// Local generated packages - resolved during Docker build
replace (
	github.com/joustmania/connect-proxy/gen/audio => ./gen/audio
	github.com/joustmania/connect-proxy/gen/controller_manager => ./gen/controller_manager
	github.com/joustmania/connect-proxy/gen/controller_manager_mock => ./gen/controller_manager_mock
	github.com/joustmania/connect-proxy/gen/game_coordinator => ./gen/game_coordinator
	github.com/joustmania/connect-proxy/gen/menu => ./gen/menu
	github.com/joustmania/connect-proxy/gen/settings => ./gen/settings
)
