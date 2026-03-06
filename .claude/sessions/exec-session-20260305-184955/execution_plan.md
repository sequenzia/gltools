# Execution Plan

Task Execution ID: exec-session-20260305-184955
Tasks to execute: 39
Retry limit: 3 per task
Max parallel: 5 per wave

## WAVE 1 (1 task)
1. [1] Set up project scaffolding with Hatch

## WAVE 2 (5 tasks)
2. [2] Create base Pydantic model and shared reference models — after [1]
3. [7] Implement configuration system with Pydantic Settings — after [1]
4. [9] Implement git remote detection for auto project resolution — after [1]
5. [16] Set up Typer CLI framework with global options — after [1]
6. [37] Configure PyPI packaging and uvx support — after [1]

## WAVE 3a (5 tasks)
7. [10] Implement GitLab HTTP client with httpx — after [7]
8. [3] Create MergeRequest Pydantic model — after [2]
9. [4] Create Issue Pydantic model — after [2]
10. [5] Create Pipeline and Job Pydantic models — after [2]
11. [6] Create output envelope models — after [2]

## WAVE 3b (2 tasks)
12. [8] Implement keyring integration for secure token storage — after [7]
13. [26] Implement plugin protocol and discovery — after [16]

## WAVE 4a (5 tasks)
14. [17] Implement output formatting system — after [16, 6]
15. [11] Implement MergeRequest resource manager — after [10, 3]
16. [12] Implement Issue resource manager — after [10, 4]
17. [13] Implement Pipeline and Job resource managers — after [10, 5]
18. [15] Set up test infrastructure with respx fixtures — after [2, 3, 4, 5, 6]

## WAVE 4b (2 tasks)
19. [21] Implement auth CLI commands — after [16, 7, 8]
20. [39] Verify multi-instance and profile support — after [7, 10]

## WAVE 5 (1 task)
21. [14] Implement GitLabClient facade — after [11, 12, 13]

## WAVE 6 (4 tasks)
22. [18] Implement MergeRequest service layer — after [14]
23. [19] Implement Issue service layer — after [14]
24. [20] Implement CI service layer — after [14]
25. [29] Set up Textual TUI application framework — after [14, 16]

## WAVE 7a (5 tasks)
26. [22] Implement MR CLI commands — after [18, 17]
27. [23] Implement Issue CLI commands — after [19, 17]
28. [24] Implement CI CLI commands — after [20, 17]
29. [30] Build TUI dashboard screen — after [29, 18, 19, 20]
30. [31] Build TUI MR list and detail screens — after [29, 18]

## WAVE 7b (4 tasks)
31. [32] Build TUI Issue list and detail screens — after [29, 19]
32. [33] Build TUI CI/pipeline status screen — after [29, 20]
33. [27] Add tests for service layers — after [15, 18, 19, 20]
34. [34] Implement TUI command palette — after [29]

## WAVE 8 (4 tasks)
35. [25] Implement dry-run mode for write commands — after [17, 22, 23, 24]
36. [28] Add tests for CLI commands — after [15, 22, 23, 24]
37. [38] Harden error handling and edge cases — after [22, 23, 24]
38. [35] Add tests for TUI screens — after [30, 31, 32, 33]

## WAVE 9 (1 task)
39. [36] Write README with installation and usage documentation — after [28, 35]
