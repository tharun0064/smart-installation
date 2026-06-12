// main.go
package main

import (
	"fmt"
	"os"

	"github.com/newrelic/nr-diagnose/cmd"
	"github.com/spf13/cobra"
)

var rootCmd = &cobra.Command{
	Use:   "nr-diagnose",
	Short: "Intelligent CLI diagnostics for New Relic agent installations",
	Long:  "An AI-powered script runner that diagnoses installation failures and suggests fixes.",
}

func init() {
	rootCmd.AddCommand(cmd.RunCmd)
	rootCmd.AddCommand(cmd.ListCmd)
	rootCmd.AddCommand(cmd.NewAgentCmd)
	rootCmd.AddCommand(cmd.SyncCmd)
}

func main() {
	if err := rootCmd.Execute(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
