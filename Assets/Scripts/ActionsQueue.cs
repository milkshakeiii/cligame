using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using UnityEngine;

public class ActionsQueue : MonoBehaviour
{
    public GameDisplayer gameDisplayer;
    public GameObject shipGhostPrefab;
    public GameObject courseLinePrefab;

    private List<string> actions = new();
    private string myShipUuid;
    private List<GameObject> courseLines = new();

    private void OnEnable()
    {
        //ServerPinger.OnZoneStateReceived += ZoneStateReceived;
        ServerPinger.OnNewShipUuidReceived += NewShipUuidReceived;
    }

    private void OnDisable()
    {
        //ServerPinger.OnZoneStateReceived -= ZoneStateReceived;
        ServerPinger.OnNewShipUuidReceived -= NewShipUuidReceived;
    }

    private void NewShipUuidReceived(string myShipUuid)
    {
        this.myShipUuid = myShipUuid;
    }

    // Start is called before the first frame update
    void Start()
    {
        
    }

    // Update is called once per frame
    void Update()
    {
        // when the mouse is clicked
        if (Input.GetMouseButtonDown(0) || Input.GetMouseButtonUp(0))
        {
            // get the world position of the mouse
            Vector3 mousePos = Camera.main.ScreenToWorldPoint(Input.mousePosition);
            mousePos.z = 0;
            Vector2Int boardPosition = new Vector2Int(Mathf.RoundToInt(mousePos.x), Mathf.RoundToInt(mousePos.y));
            if (Input.GetMouseButtonDown(0))
            {
                MouseDown(boardPosition);
            }
            else
            {
                MouseUp(boardPosition);
            }
        }
    }

    private Vector3 BoardPositionToWorldPosition(Vector2Int boardPosition)
    {
        return new Vector3(boardPosition.x, boardPosition.y, 0);
    }

    private void MouseUp(Vector2Int _)
    {
        return;
    }

    private void MouseDown(Vector2Int boardPosition)
    {
        StartCoroutine(MoveCommandCoroutine(boardPosition));
    }

    private IEnumerator MoveCommandCoroutine(Vector2Int targetPosition)
    {
        Tuple<string, Vector2Int> currentPositionAndFacing = gameDisplayer.GetFacingAndPosition(myShipUuid);
        Vector2Int currentPosition = currentPositionAndFacing.Item2;
        string currentFacing = currentPositionAndFacing.Item1;
        if (Input.GetKey(KeyCode.LeftShift))
        {
            currentPosition = FacingAndPositionAtEndOfQueue().Item2;
        }
        string targetFacing = NaturalFacingForMove(currentPosition, targetPosition);

        GameObject ghostShip = Instantiate(shipGhostPrefab, BoardPositionToWorldPosition(currentPosition), Quaternion.identity);
        Ship.Initialize(ghostShip, targetFacing, currentPosition);
        List<string> pendingCommands = CommandsAfterInput(targetPosition, targetFacing);
        ShowActionLine(pendingCommands);

        while (Input.GetMouseButton(0))
        {
            yield return null;
            // a and d should rotate the ghost ship
            if (Input.GetKey(KeyCode.A))
            {
                targetFacing = GameDisplayer.GetLeftFacing(targetFacing);
                Ship.Initialize(ghostShip, targetFacing, currentPosition);
                pendingCommands = CommandsAfterInput(targetPosition, targetFacing);
                ShowActionLine(pendingCommands);
            }
            else if (Input.GetKey(KeyCode.D))
            {
                targetFacing = GameDisplayer.GetLeftFacing(targetFacing);
                Ship.Initialize(ghostShip, targetFacing, currentPosition);
                pendingCommands = CommandsAfterInput(targetPosition, targetFacing);
                ShowActionLine(pendingCommands);
            }
        }

        Destroy(ghostShip);
        SetAndReportActions(pendingCommands);
    }

    private void ShowActionLine(List<string> pendingCommands)
    {
        foreach (GameObject courseLine in courseLines)
        {
            Destroy(courseLine);
        }
        courseLines.Clear();

        Vector2Int currentPosition = gameDisplayer.GetFacingAndPosition(myShipUuid).Item2;
        Vector2Int lastPosition = currentPosition;
        string currentFacing = gameDisplayer.GetFacingAndPosition(myShipUuid).Item1;
        foreach (string command in pendingCommands)
        {
            // TODO start here
            Vector2Int nextPosition = currentPosition;
            if (command == "step")
                nextPosition += GameDisplayer.GetFacingVector(currentFacing);
            GameObject courseLine = Instantiate(courseLinePrefab, BoardPositionToWorldPosition(currentPosition), Quaternion.identity);
            courseLine.GetComponent<CourseLine>().Initialize(BoardPositionToWorldPosition(currentPosition), BoardPositionToWorldPosition(nextPosition));
            currentPosition = nextPosition;
            if (command == "right")
                currentFacing = GameDisplayer.GetRightFacing(currentFacing);
            else if (command == "left")
                currentFacing = GameDisplayer.GetLeftFacing(currentFacing);
            courseLines.Add(courseLine);
        }
    }
    
    private string NaturalFacingForMove(Vector2Int currentPosition, Vector2Int targetPosition)
    {
        Vector2Int delta = targetPosition - currentPosition;
        if (delta.x > 0)
        {
            return "right";
        }
        else if (delta.x < 0)
        {
            return "left";
        }
        else if (delta.y > 0)
        {
            return "up";
        }
        else if (delta.y < 0)
        {
            return "down";
        }
        else
        {
            return "up";
        }
    }

    private List<string> CommandsAfterInput(Vector2Int targetPosition, string targetFacing)
    {
        List<string> newCommands;
        if (Input.GetKey(KeyCode.LeftShift))
        {
            // start from the end of the current actions queue
            Tuple<string, Vector2Int> facingAndPositionAtEndOfQueue = FacingAndPositionAtEndOfQueue();
            newCommands = new();
            newCommands.AddRange(actions);
            newCommands.AddRange(gameDisplayer.GetActionsToReachPoint(myShipUuid, facingAndPositionAtEndOfQueue.Item2, facingAndPositionAtEndOfQueue.Item1, targetPosition, targetFacing));
        }
        else
        {
            // start from the current position and facing
            Tuple<string, Vector2Int> facingAndPosition = gameDisplayer.GetFacingAndPosition(myShipUuid);
            newCommands = gameDisplayer.GetActionsToReachPoint(myShipUuid, facingAndPosition.Item2, facingAndPosition.Item1, targetPosition, targetFacing);
        }
        return newCommands;
    }

    private void FinalizeCommand(string targetFacing, Vector2Int targetBoardPosition)
    {
        if (Input.GetKey(KeyCode.LeftShift))
        {
            // start from the end of the current actions queue
            Tuple<string, Vector2Int> facingAndPositionAtEndOfQueue = FacingAndPositionAtEndOfQueue();
            QueueCommand(facingAndPositionAtEndOfQueue.Item2, facingAndPositionAtEndOfQueue.Item1, targetBoardPosition, targetFacing);
        }
        else
        {
            actions.Clear();
            // start from the current position and facing
            Tuple<string, Vector2Int> facingAndPosition = gameDisplayer.GetFacingAndPosition(myShipUuid);
            QueueCommand(facingAndPosition.Item2, facingAndPosition.Item1, targetBoardPosition, targetFacing);
        }
    }

    private Tuple<string, Vector2Int> FacingAndPositionAtEndOfQueue()
    {
        Tuple<string, Vector2Int> currentPositionAndFacing = gameDisplayer.GetFacingAndPosition(myShipUuid);
        Vector2Int currentPosition = currentPositionAndFacing.Item2;
        string currentFacing = currentPositionAndFacing.Item1;
        foreach (string action in actions)
        {
            if (action.StartsWith("step"))
            {
                currentPosition += GameDisplayer.GetFacingVector(currentFacing);
            }
            else if (action.StartsWith("left"))
            {
                currentFacing = GameDisplayer.GetLeftFacing(currentFacing);
            }
            else if (action.StartsWith("right"))
            {
                currentFacing = GameDisplayer.GetRightFacing(currentFacing);
            }
        }
        return new Tuple<string, Vector2Int>(currentFacing, currentPosition);
    }

    private void QueueCommand(Vector2Int startingPosition, string startingFacing, Vector2Int targetPosition, string targetFacing)
    {
        List<string> newCommands = gameDisplayer.GetActionsToReachPoint(myShipUuid, startingPosition, startingFacing, targetPosition, targetFacing);
        SetAndReportActions(newCommands);
    }

    private void SetAndReportActions(List<string> newActions)
    {
        actions = newActions;
        string actionsString = string.Join(',', newActions);
        // TODO: report actions to server
    }
}
