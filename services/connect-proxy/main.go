// Connect-Go Proxy for JoustMania
//
// This service acts as a bridge between the browser (Connect protocol over HTTP/1.1)
// and the backend gRPC services. It enables real-time streaming to the web dashboard.
package main

import (
	"context"
	"io"
	"log"
	"net/http"
	"os"

	"connectrpc.com/connect"
	"github.com/rs/cors"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"

	// Generated proto imports
	controllerpb "github.com/joustmania/connect-proxy/gen/controller_manager"
	gamepb "github.com/joustmania/connect-proxy/gen/game_coordinator"
	menupb "github.com/joustmania/connect-proxy/gen/menu"
	settingspb "github.com/joustmania/connect-proxy/gen/settings"

	// Connect handlers
	"github.com/joustmania/connect-proxy/gen/controller_manager/controller_managerconnect"
	"github.com/joustmania/connect-proxy/gen/game_coordinator/game_coordinatorconnect"
	"github.com/joustmania/connect-proxy/gen/menu/menuconnect"
	"github.com/joustmania/connect-proxy/gen/settings/settingsconnect"
)

// Service addresses from environment or defaults
var (
	controllerManagerAddr = getEnv("CONTROLLER_MANAGER_SERVICE", "controller-manager:50052")
	gameCoordinatorAddr   = getEnv("GAME_COORDINATOR_SERVICE", "game-coordinator:50053")
	menuAddr              = getEnv("MENU_SERVICE", "menu:50054")
	settingsAddr          = getEnv("SETTINGS_SERVICE", "settings:50051")
	listenAddr            = getEnv("LISTEN_ADDR", ":8080")
)

func getEnv(key, defaultValue string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return defaultValue
}

func main() {
	log.Println("JoustMania Connect Proxy starting...")
	log.Printf("Controller Manager: %s", controllerManagerAddr)
	log.Printf("Game Coordinator: %s", gameCoordinatorAddr)
	log.Printf("Menu: %s", menuAddr)
	log.Printf("Settings: %s", settingsAddr)

	// Create gRPC connections to backend services
	controllerConn, err := grpc.NewClient(controllerManagerAddr, grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		log.Fatalf("Failed to connect to controller manager: %v", err)
	}
	defer controllerConn.Close()

	gameConn, err := grpc.NewClient(gameCoordinatorAddr, grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		log.Fatalf("Failed to connect to game coordinator: %v", err)
	}
	defer gameConn.Close()

	menuConn, err := grpc.NewClient(menuAddr, grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		log.Fatalf("Failed to connect to menu: %v", err)
	}
	defer menuConn.Close()

	settingsConn, err := grpc.NewClient(settingsAddr, grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		log.Fatalf("Failed to connect to settings: %v", err)
	}
	defer settingsConn.Close()

	// Create gRPC clients
	controllerClient := controllerpb.NewControllerManagerServiceClient(controllerConn)
	gameClient := gamepb.NewGameCoordinatorServiceClient(gameConn)
	menuClient := menupb.NewMenuServiceClient(menuConn)
	settingsClient := settingspb.NewSettingsServiceClient(settingsConn)

	// Create HTTP mux with Connect handlers
	mux := http.NewServeMux()

	// Register Connect handlers for each service
	controllerPath, controllerHandler := controller_managerconnect.NewControllerManagerServiceHandler(
		&ControllerManagerProxy{client: controllerClient},
	)
	mux.Handle(controllerPath, controllerHandler)

	gamePath, gameHandler := game_coordinatorconnect.NewGameCoordinatorServiceHandler(
		&GameCoordinatorProxy{client: gameClient},
	)
	mux.Handle(gamePath, gameHandler)

	menuPath, menuHandler := menuconnect.NewMenuServiceHandler(
		&MenuProxy{client: menuClient},
	)
	mux.Handle(menuPath, menuHandler)

	settingsPath, settingsHandler := settingsconnect.NewSettingsServiceHandler(
		&SettingsProxy{client: settingsClient},
	)
	mux.Handle(settingsPath, settingsHandler)

	// Health check endpoint
	mux.HandleFunc("/health", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		w.Write([]byte("OK"))
	})

	// Serve static files for dashboard (if mounted)
	staticDir := "/app/static"
	if _, err := os.Stat(staticDir); err == nil {
		log.Printf("Serving static files from %s", staticDir)
		mux.Handle("/", http.FileServer(http.Dir(staticDir)))
	}

	// CORS middleware for browser requests
	corsHandler := cors.New(cors.Options{
		AllowedOrigins:   []string{"*"},
		AllowedMethods:   []string{"GET", "POST", "OPTIONS"},
		AllowedHeaders:   []string{"*"},
		AllowCredentials: false,
		MaxAge:           86400,
	}).Handler(mux)

	// Start server
	log.Printf("Connect proxy listening on %s", listenAddr)
	if err := http.ListenAndServe(listenAddr, corsHandler); err != nil {
		log.Fatalf("Server failed: %v", err)
	}
}

// ControllerManagerProxy implements the Connect handler by proxying to gRPC
type ControllerManagerProxy struct {
	client controllerpb.ControllerManagerServiceClient
}

func (p *ControllerManagerProxy) StreamButtonEvents(
	ctx context.Context,
	stream *connect.BidiStream[controllerpb.ButtonEventStreamControl, controllerpb.ButtonEvent],
) error {
	// For bidirectional streaming, we need to handle both directions
	grpcStream, err := p.client.StreamButtonEvents(ctx)
	if err != nil {
		return connect.NewError(connect.CodeInternal, err)
	}

	// Forward messages in both directions
	errCh := make(chan error, 2)

	// Client -> gRPC
	go func() {
		for {
			msg, err := stream.Receive()
			if err == io.EOF {
				grpcStream.CloseSend()
				errCh <- nil
				return
			}
			if err != nil {
				errCh <- err
				return
			}
			if err := grpcStream.Send(msg); err != nil {
				errCh <- err
				return
			}
		}
	}()

	// gRPC -> Client
	go func() {
		for {
			msg, err := grpcStream.Recv()
			if err == io.EOF {
				errCh <- nil
				return
			}
			if err != nil {
				errCh <- err
				return
			}
			if err := stream.Send(msg); err != nil {
				errCh <- err
				return
			}
		}
	}()

	// Wait for either direction to finish
	return <-errCh
}

func (p *ControllerManagerProxy) StreamGameplayData(
	ctx context.Context,
	stream *connect.BidiStream[controllerpb.GameplayStreamControl, controllerpb.GameplayDataUpdate],
) error {
	grpcStream, err := p.client.StreamGameplayData(ctx)
	if err != nil {
		return connect.NewError(connect.CodeInternal, err)
	}

	errCh := make(chan error, 2)

	// Client -> gRPC
	go func() {
		for {
			msg, err := stream.Receive()
			if err == io.EOF {
				grpcStream.CloseSend()
				errCh <- nil
				return
			}
			if err != nil {
				errCh <- err
				return
			}
			if err := grpcStream.Send(msg); err != nil {
				errCh <- err
				return
			}
		}
	}()

	// gRPC -> Client
	go func() {
		for {
			msg, err := grpcStream.Recv()
			if err == io.EOF {
				errCh <- nil
				return
			}
			if err != nil {
				errCh <- err
				return
			}
			if err := stream.Send(msg); err != nil {
				errCh <- err
				return
			}
		}
	}()

	return <-errCh
}

func (p *ControllerManagerProxy) RenameController(
	ctx context.Context,
	req *connect.Request[controllerpb.RenameControllerRequest],
) (*connect.Response[controllerpb.RenameControllerResponse], error) {
	resp, err := p.client.RenameController(ctx, req.Msg)
	if err != nil {
		return nil, connect.NewError(connect.CodeInternal, err)
	}
	return connect.NewResponse(resp), nil
}

// GameCoordinatorProxy implements the Connect handler by proxying to gRPC
type GameCoordinatorProxy struct {
	client gamepb.GameCoordinatorServiceClient
}

func (p *GameCoordinatorProxy) ForceEndGame(
	ctx context.Context,
	req *connect.Request[gamepb.ForceEndGameRequest],
) (*connect.Response[gamepb.ForceEndGameResponse], error) {
	resp, err := p.client.ForceEndGame(ctx, req.Msg)
	if err != nil {
		return nil, connect.NewError(connect.CodeInternal, err)
	}
	return connect.NewResponse(resp), nil
}

func (p *GameCoordinatorProxy) StreamGameEvents(
	ctx context.Context,
	req *connect.Request[gamepb.StreamEventsRequest],
	stream *connect.ServerStream[gamepb.GameEvent],
) error {
	grpcStream, err := p.client.StreamGameEvents(ctx, req.Msg)
	if err != nil {
		return connect.NewError(connect.CodeInternal, err)
	}

	for {
		msg, err := grpcStream.Recv()
		if err == io.EOF {
			return nil
		}
		if err != nil {
			return connect.NewError(connect.CodeInternal, err)
		}
		if err := stream.Send(msg); err != nil {
			return err
		}
	}
}

func (p *GameCoordinatorProxy) GetGameState(
	ctx context.Context,
	req *connect.Request[gamepb.GetGameStateRequest],
) (*connect.Response[gamepb.GetGameStateResponse], error) {
	resp, err := p.client.GetGameState(ctx, req.Msg)
	if err != nil {
		return nil, connect.NewError(connect.CodeInternal, err)
	}
	return connect.NewResponse(resp), nil
}

// MenuProxy implements the Connect handler by proxying to gRPC
type MenuProxy struct {
	client menupb.MenuServiceClient
}

func (p *MenuProxy) StartMenu(
	ctx context.Context,
	req *connect.Request[menupb.StartMenuRequest],
) (*connect.Response[menupb.StartMenuResponse], error) {
	resp, err := p.client.StartMenu(ctx, req.Msg)
	if err != nil {
		return nil, connect.NewError(connect.CodeInternal, err)
	}
	return connect.NewResponse(resp), nil
}

func (p *MenuProxy) StopMenu(
	ctx context.Context,
	req *connect.Request[menupb.StopMenuRequest],
) (*connect.Response[menupb.StopMenuResponse], error) {
	resp, err := p.client.StopMenu(ctx, req.Msg)
	if err != nil {
		return nil, connect.NewError(connect.CodeInternal, err)
	}
	return connect.NewResponse(resp), nil
}

func (p *MenuProxy) StreamMenuEvents(
	ctx context.Context,
	req *connect.Request[menupb.StreamMenuEventsRequest],
	stream *connect.ServerStream[menupb.MenuEvent],
) error {
	grpcStream, err := p.client.StreamMenuEvents(ctx, req.Msg)
	if err != nil {
		return connect.NewError(connect.CodeInternal, err)
	}

	for {
		msg, err := grpcStream.Recv()
		if err == io.EOF {
			return nil
		}
		if err != nil {
			return connect.NewError(connect.CodeInternal, err)
		}
		if err := stream.Send(msg); err != nil {
			return err
		}
	}
}

func (p *MenuProxy) ProcessInput(
	ctx context.Context,
	req *connect.Request[menupb.ProcessInputRequest],
) (*connect.Response[menupb.ProcessInputResponse], error) {
	resp, err := p.client.ProcessInput(ctx, req.Msg)
	if err != nil {
		return nil, connect.NewError(connect.CodeInternal, err)
	}
	return connect.NewResponse(resp), nil
}

// SettingsProxy implements the Connect handler by proxying to gRPC
type SettingsProxy struct {
	client settingspb.SettingsServiceClient
}

func (p *SettingsProxy) GetSettings(
	ctx context.Context,
	req *connect.Request[settingspb.GetSettingsRequest],
) (*connect.Response[settingspb.GetSettingsResponse], error) {
	resp, err := p.client.GetSettings(ctx, req.Msg)
	if err != nil {
		return nil, connect.NewError(connect.CodeInternal, err)
	}
	return connect.NewResponse(resp), nil
}

func (p *SettingsProxy) GetSetting(
	ctx context.Context,
	req *connect.Request[settingspb.GetSettingRequest],
) (*connect.Response[settingspb.GetSettingResponse], error) {
	resp, err := p.client.GetSetting(ctx, req.Msg)
	if err != nil {
		return nil, connect.NewError(connect.CodeInternal, err)
	}
	return connect.NewResponse(resp), nil
}

func (p *SettingsProxy) UpdateSetting(
	ctx context.Context,
	req *connect.Request[settingspb.UpdateSettingRequest],
) (*connect.Response[settingspb.UpdateSettingResponse], error) {
	resp, err := p.client.UpdateSetting(ctx, req.Msg)
	if err != nil {
		return nil, connect.NewError(connect.CodeInternal, err)
	}
	return connect.NewResponse(resp), nil
}

func (p *SettingsProxy) SubscribeToChanges(
	ctx context.Context,
	req *connect.Request[settingspb.SubscribeRequest],
	stream *connect.ServerStream[settingspb.SettingChangeEvent],
) error {
	grpcStream, err := p.client.SubscribeToChanges(ctx, req.Msg)
	if err != nil {
		return connect.NewError(connect.CodeInternal, err)
	}

	for {
		msg, err := grpcStream.Recv()
		if err == io.EOF {
			return nil
		}
		if err != nil {
			return connect.NewError(connect.CodeInternal, err)
		}
		if err := stream.Send(msg); err != nil {
			return err
		}
	}
}
