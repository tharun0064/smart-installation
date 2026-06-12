// cmd/sync.go
package cmd

import (
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"strings"

	"github.com/newrelic/nr-diagnose/internal/config"
	"github.com/spf13/cobra"
)

var SyncCmd = &cobra.Command{
	Use:   "sync",
	Short: "Sync local runbook entries to the shared repository",
	RunE: func(cmd *cobra.Command, args []string) error {
		cfg, _ := config.Load()

		localRunbookBase := filepath.Join(cfg.LocalData, "runbook")
		if _, err := os.Stat(localRunbookBase); err != nil {
			fmt.Println("No local runbook entries to sync.")
			return nil
		}

		agentsDir := cfg.AgentsDir
		if agentsDir == "" {
			agentsDir = filepath.Join(".", "agents")
		}

		entries, err := os.ReadDir(localRunbookBase)
		if err != nil {
			return err
		}

		totalCopied := 0
		for _, entry := range entries {
			if !entry.IsDir() {
				continue
			}
			agentName := entry.Name()
			localDir := filepath.Join(localRunbookBase, agentName)
			repoDir := filepath.Join(agentsDir, agentName, "runbook")

			if _, err := os.Stat(repoDir); err != nil {
				fmt.Printf("  Skipping %s (agent not in repo)\n", agentName)
				continue
			}

			// Copy .md files from local to repo
			files, _ := os.ReadDir(localDir)
			for _, f := range files {
				if f.IsDir() || !strings.HasSuffix(f.Name(), ".md") {
					continue
				}
				src := filepath.Join(localDir, f.Name())
				dst := filepath.Join(repoDir, f.Name())
				if _, err := os.Stat(dst); err == nil {
					continue // already exists
				}
				if err := copyFile(src, dst); err == nil {
					totalCopied++
				}
			}

			// Copy index.yaml (merge would be better but this is prototype)
			localIndex := filepath.Join(localDir, "index.yaml")
			if _, err := os.Stat(localIndex); err == nil {
				copyFile(localIndex, filepath.Join(repoDir, "index.yaml"))
			}
		}

		if totalCopied == 0 {
			fmt.Println("No new entries to sync.")
			return nil
		}

		fmt.Printf("Copied %d runbook entries to repo.\n", totalCopied)

		// Git add + commit
		gitAdd := exec.Command("git", "add", agentsDir)
		if err := gitAdd.Run(); err != nil {
			fmt.Println("Note: git add failed — stage and commit manually.")
			return nil
		}

		msg := fmt.Sprintf("runbook: sync %d local entries", totalCopied)
		gitCommit := exec.Command("git", "commit", "-m", msg)
		if err := gitCommit.Run(); err != nil {
			fmt.Println("Note: git commit failed — commit manually.")
			return nil
		}

		fmt.Printf("Committed. Run 'git push' to share with team.\n")
		return nil
	},
}

func copyFile(src, dst string) error {
	in, err := os.Open(src)
	if err != nil {
		return err
	}
	defer in.Close()

	out, err := os.Create(dst)
	if err != nil {
		return err
	}
	defer out.Close()

	_, err = io.Copy(out, in)
	return err
}
